# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from collections import defaultdict
import fire
import common, torch
from pathlib import Path
from typing import List, Optional
from time import time 
from common import GeneratorType, SourceType, setup_logging
from code_miner import get_code_miner
from baselines.daikon import DaikonGenerator
from function_data import FunctionData
from spec import Postcondition
from tester.contract_tester import ContractTester
from tester import get_contract_tester
from llm_generator.fs_generator import FSGenerator
import logging
logger = logging.getLogger(__name__)

def run(
        source, 
        model_name:str, 
        return_type:str='int', 
        use_cache:bool=True, 
        count:int=100, 
        timeout:float=60, 
        add_doc:bool=False,
        add_cot: bool=True,
        add_ret_type: bool=True,
        few_shot:int=4,
        use_quantifiers:bool=False,
        debug_example_id:Optional[int]=None,
        gen_name:str='fun2spec',
        quant_bits:Optional[int]=None,
        reprompt:bool=False,
        max_new_tokens:int=400,
        nl2post=False,
        **kwargs
    ):
    setup_logging()

    # Check all provided arguments are expected
    assert len(kwargs) == 0, f"Invalid arguments {kwargs}"

    source_type: SourceType = common.get_source_name(source)
    logger.info(f"Analyzing {source_type}...")

    # Code in the repository is analyzed to extract the functions and relevant metadata
    miner = get_code_miner(source=source, use_cache=use_cache)

    # For BDE and humaneval docstring is available, and thus we filter functions with docstring
    with_docstring = source_type in [SourceType.humaneval, SourceType.BDE]

    # Filter functions according to the return type
    filtered_functions = miner.filter_by_return_type(return_type=return_type, with_docstring=with_docstring)
    logger.info(f"Filtered {len(filtered_functions)} functions. In the evaluation, {min(count, len(filtered_functions))} will be used.")

    # Create the specification generator
    spec_gen_class = common.get_generator(gen_name)
    if spec_gen_class == GeneratorType.Fun2Spec:
        spec_generator = FSGenerator(
            model_name=model_name, 
            add_doc=add_doc, 
            add_cot=add_cot, 
            add_ret_type=add_ret_type, 
            use_quantifiers=use_quantifiers, 
            few_shot=few_shot, 
            quant_bits=quant_bits,
            max_new_tokens=max_new_tokens,
            nl2post=nl2post
            )
    else:
        if source_type == SourceType.file \
            or source_type == SourceType.humaneval:
            spec_generator = DaikonGenerator()
        else:
            raise ValueError(f'Generator {spec_gen_class} is not implemented yet for {source_type}!')

    # Prepare the tester
    ctester = get_contract_tester(
        source_type, root_dir=source, timeout=timeout, use_cache=use_cache)
    
    # Filter functions with test target
    if 'filter_fns_with_test_target' in dir(ctester):
        filtered_functions = ctester.filter_fns_with_test_target(filtered_functions)
        logger.info(f"Extracted {len(filtered_functions)} functions with test targets.")

    if debug_example_id is not None:
        filtered_functions = [filtered_functions[debug_example_id]]
    
    meta_stats = defaultdict(int)    
    sum_test_time, cnt_fns_tested, sum_gen_time = 0, 0, 0
    task_to_post, results, raw_gens, all_posts = {}, [], [], []
    filtered_functions = filtered_functions[:count]
    count = len(filtered_functions[:count])

    total_memory = torch.cuda.get_device_properties(0).total_memory
    allocated_memory = torch.cuda.memory_allocated(0)
    free_memory = (total_memory - allocated_memory)/(1024**3)
    logger.info(f"Free GPU memory: {free_memory:.2f} GB")    

    for idx in range(count): 
        # Generation of postcondition
        test_time, gen_time = generate_post(
            idx, reprompt, filtered_functions, spec_generator, 
            ctester, meta_stats, task_to_post, results, raw_gens, all_posts,
            nl2post=nl2post
            )
        sum_gen_time += gen_time
        sum_test_time += test_time
        cnt_fns_tested += 1

    meta_stats['avg_gen_time'] = str(round(sum_gen_time/len(filtered_functions[:count]), 2))
    meta_stats['avg_test_time'] = str(round(sum_test_time/cnt_fns_tested, 2))

    # Read the output and compute statistics
    if source_type != SourceType.file:
        compute_stats(
            source,
            results, 
            len(filtered_functions[:count]), 
            task_to_post,
            model_name=model_name, 
            return_type=return_type, 
            use_cache=use_cache, 
            count=count, 
            timeout=timeout, 
            add_doc=add_doc,
            add_cot=add_cot,
            few_shot=few_shot,
            add_ret_type=add_ret_type,
            use_quantifiers=use_quantifiers,
            gen_name=gen_name,
            raw_gens=raw_gens,
            meta_stats=meta_stats,
            reprompt=reprompt,
            **kwargs
        )

def generate_post(
        idx:int,
        reprompt:bool, 
        filtered_functions:List, 
        spec_generator:FSGenerator, 
        ctester:ContractTester, 
        meta_stats:dict, 
        task_to_post:dict, 
        results: List, 
        raw_gens: List, 
        all_posts: List,
        nl2post:bool=False
    ):
    logger.info(f"Example {idx+1} {'-'*50}")
    start_time = time()
    batch_fns = filtered_functions[idx]
    post, raw_post = spec_generator.get_postcondition([batch_fns])[0]
    raw_gens.append(raw_post)

    # Store time for generation
    gen_time = time()-start_time
    logger.info(f"Time for invariant generation: {round(gen_time, 2)}")

    test_time = 0
    fn_data = filtered_functions[idx]

    # Test the generated postcondition
    result = None
    task_to_post[idx] = post
    result = test_post(ctester, meta_stats, post, fn_data, nl2post)

    # Reprompt if enabled
    if result is not None and result['result'] == 'Compilation error' and reprompt and not nl2post:
        logger.info(f"Reprompting due to {result['result']}")
        new_post, raw_post = spec_generator.get_postcondition(
                [batch_fns], 
                prev_result=result
                )[0]

        result = test_post(ctester, meta_stats, new_post, fn_data, nl2post)

    if result is not None:
        results.append(result)

    all_posts.append(post)
    logger.info(f"Total time for testing postcondition: {round(test_time, 2)}")
    return test_time, gen_time


def test_post(ctester, meta_stats, post: Postcondition, fn_data: FunctionData, nl2post=False):
    result = None
    if post is not None:
        if post.predicate is not None:
            if nl2post:
                cpp_expr = post.predicate
            else:
                cpp_expr = post.get_cpp_expression()

            if cpp_expr is not None:
                result = ctester.check_assertion(fn_data, cpp_expr)
                result['postcondition'] = post.predicate

                logger.info("Reasoning:")
                print(post.reasoning)

                logger.info("Postcondition:")
                print(post.predicate)
            else:
                # In this case the postcondition cannot be translated correctly
                meta_stats['cannot_translate'] += 1
                logger.info("Cannot translate the postcondition!")
        else:
            # Unable to extract the postcondition from the output
            meta_stats['cannot_parse'] += 1
            logger.info("Cannot parse the postcondition!")
    return result


def compute_stats(
        source,
        results: dict, 
        total, 
        task_to_post,
        model_name:str="microsoft/Phi-3-mini-128k-instruct", 
        return_type:str='int', 
        use_cache:bool=True, 
        count:int=50, 
        timeout:float=30, 
        add_doc:bool=False,
        add_cot: bool=True,
        add_ret_type: bool=True,
        use_quantifiers: bool=True,
        gen_name:str='fun2spec',
        raw_gens=[],
        meta_stats=None,
        few_shot=4,
        reprompt=False,
        **kwargs
        ):
        """
        Read the output in result.jsonl file and and compute statistics
        """
        # Copy result file path in another place
        log_path = f"{common.get_project_path()}/data/{common.get_source_name(source)}/{model_name}/"
        log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}_cot:{add_cot}_ret:{add_ret_type}_few_shot:{few_shot}"
        log_file_name += f"_us_quantifiers:{use_quantifiers}"
        
        log_res_path = f"{log_path}/{log_file_name}.jsonl"
        log_raw_gens = f"{log_path}/{log_file_name}_raw_output.txt"
        
        Path(log_path).mkdir(parents=True, exist_ok=True)

        # Store raw generation
        with open(log_raw_gens, 'w') as f:
            for line in raw_gens:
                f.write(f"{line}\n")   

        count_test_valid, count_test_invalid, count_clang_issue, count_no_test, count_compile_error = 0, 0, 0, 0, 0
        count_total = 0

        with open(log_res_path, 'w') as lf:
            for idx, result in enumerate(results):
                # res_json = json.loads(res.replace("'", "\""))
                cnt_true, cnt_false, return_code = result['true'], result['false'], result['return_code']
                cnt_true, cnt_false = int(cnt_true), int(cnt_false)

                count_test_valid += (result["result"] == True)
                count_test_invalid += (result["result"] == False)
                count_no_test += (result['result'] == "No test")
                count_clang_issue += (result['result'] == "Clang Error")
                count_compile_error += (result['result'] == "Compilation error")
                count_total += (result["result"] == True or result["result"] == False or result['result'] == "Compilation error")

                if idx in task_to_post:
                    # Add reasoning in the output if it was parsed correctly in the output
                    result['reasoning'] = task_to_post[idx].reasoning

                # Store the updated JSON back to the new result log file
                lf.write(str(result) + '\n')

        count_total = count_total + meta_stats['cannot_parse'] + meta_stats['cannot_translate']

        # print(f"Postcondition generated for: {len(results)}/{count_total}")
        print(f"Does not compile, timeout reached: {count_compile_error}/{count_total}")
        print(f"No test exists: {count_no_test}/{count_total}")

        print(f"Postcondition always hold: {count_test_valid}/{count_total}")
        print(f"Postcondition does not hold in some cases: {count_test_invalid}/{count_total}")
        
        print(f"Check more detailed results in {log_res_path}")

        # Store the result summary in a file
        result_summary = {
            "source": source,
            "model_name": model_name,
            "gen_name": gen_name,
            "return_type": return_type,
            "use_cache": use_cache,
            "count": count,
            "Postcondition test-valid": f"{count_test_valid}",
            "Postcondition test-invalid": f"{count_test_invalid}",
            "Compile Error": f"{count_compile_error}",
            "Clang Error": f"{count_clang_issue}",
            "No test exists": f"{count_no_test}",
            "meta stats": meta_stats,
            "timeout": timeout,
            "add_doc": add_doc,
            "add_cot": add_cot,
            "add_ret_type": add_ret_type,
            "use_quantifiers": use_quantifiers,
            "few_shot": few_shot,
            "reprompt": reprompt
        }
        print(result_summary)
        
        # Add a line to the results file
        with open('data/results.jsonl', 'a') as f:
            f.write(str(result_summary) + '\n')


if __name__ == "__main__":
    fire.Fire(run)
