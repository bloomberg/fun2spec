# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
This file stores the tempalte for prompts used for LLM generation.
"""
import jinja2
import jsonlines, os
import common
from function_data import FunctionData
from code_miner.ts_parser import get_ts_fn_node_docstring, get_all_ts_function_nodes
from code_miner.clang_parser import get_all_functions_clang

# Instructtion
post_prompt_instruction = """As an expert language model trained in understanding code, your task is to generate a postcondition (POST) for the provided C++ function. 
A postcondition is a predicate wrapped in POST(any_predicate) that represents a condition guaranteed to be true after the function returns.
Follow these rules to construct the postcondition:

1. Syntax: Wrap the postcondition in POST(any_predicate).
2. Implications: Use the symbol “==>” for logical implication. For example, condition1 ==> condition2 indicates that if condition1 is true, then condition2 must also be true.
3. Logical Operators: You may use “&&” (logical AND) and “||” (logical OR) to combine multiple conditions within a single predicate. condition1 && condition2 indicates that both conditions must be true. condition1 || condition2 indicates that at least one of the conditions is true.
4. All predicates used in postcondition should be valid C++ expressions. All predicates will be executed using C++ compiler. 
5. Valid Function Names: All function/method calls used in the predicate should exist in the context of the function. Do not hallucinate use and any hypothetical function name!
6. Naming the Return Value: Use "res_tmp" as the name of the return value.
7. Trivial Postcondition: If no specific predicates must hold for the function, return a trivial postcondition, POST(true).
8. Single Postcondition: Return only one postcondition per function.
9. Always include the appropriate namespace in postconditions if the constant, type, or function is qualified with a namespace in the code. If no namespace is used in the code, refer to the constant or type directly without a namespace in the postcondition.
"""

# Instructtion with quantifiers
post_prompt_instruction_quantifiers = """As an expert language model trained in understanding code, your task is to generate a postcondition (POST) for the provided C++ function. 
A postcondition is a predicate wrapped in POST(any_predicate) that represents a condition guaranteed to be true after the function returns.
Follow these rules to construct the postcondition:

1. Syntax: Wrap the postcondition in POST(any_predicate).
2. Implications: Use the symbol “==>” for logical implication. For example, condition1 ==> condition2 indicates that if condition1 is true, then condition2 must also be true.
3. Logical Operators: You may use “&&” (logical AND) and “||” (logical OR) to combine multiple conditions within a single predicate. condition1 && condition2 indicates that both conditions must be true. condition1 || condition2 indicates that at least one of the conditions is true.
4. Quantifiers: You may use EXISTS and FORALL to express quantified conditions:
   - EXISTS(start, end, var, condition): There exists a value var in range [start, end) that satisfies condition
   - FORALL(start, end, var, condition): All values var in range [start, end) satisfy condition
   
   Example: POST(res_tmp == true ==> EXISTS(0, numbers.size(), i, numbers[i] == target))
5. All predicates used in postcondition should be valid C++ expressions. All predicates will be executed using C++ compiler. 
6. Valid Function Names: All function/method calls used in the predicate should exist in the context of the function. Do not hallucinate use and any hypothetical function name! Instead give a simpler postcondition.
7. Naming the Return Value: Use "res_tmp" as the name of the return value.
8. Trivial Postcondition: If no specific predicates must hold for the function, return a trivial postcondition, POST(true).
9. Single Postcondition: Return only one postcondition per function.
10. Always include the appropriate namespace in postconditions if the constant, type, or function is qualified with a namespace in the code. If no namespace is used in the code, refer to the constant or type directly without a namespace in the postcondition.
"""

# This is taken from https://arxiv.org/pdf/2310.01831
post_prompt_instruction_nl2post = """Write a symbolic postcondition for {} consisting of exactly one postcondition statement
wrapped in POST(assertion). For variables, use only the function input parameters and a hypothetical 
return value, which we will assume to be stored in variable "res_tmp". If the postcondition calls any 
functions to external to the program context they should be only be those from the functional subsets 
of C++. By this, we mean functions that are pure (i.e., no side effects) such as:
"""


def build_prompt(
        target_fn_data: FunctionData, 
        tokenizer,
        few_shot=4, 
        add_doc=False, 
        add_cot=True, 
        add_ret_type=True, 
        quantifier_prompt=True,
        prev_result=None,
        nl2post=False
        ) -> str:
    """
    Takes the examples from examples.jsonl file and builds the prompt.
    """

    # Build few shot examples
    examples_dir = os.path.dirname(os.path.realpath(__file__))+'/fewshot_examples/'

    # Load the example list from the jsonlines file
    with jsonlines.open(examples_dir+'example_list.jsonl', 'r') as jsonl_f:
        examples = [obj for obj in jsonl_f]

    # Use first `few_shot` examples from the json
    examples = examples[:few_shot]
    fs_examples = []

    for i in range(len(examples)):
        fs_example, fs_out = build_fewshot_example(add_doc, add_cot, add_ret_type, examples_dir, examples, i)
        fs_examples.append((fs_example, fs_out))

    
    if not nl2post:
        if quantifier_prompt:
            instruction = post_prompt_instruction_quantifiers
        else:
            instruction = post_prompt_instruction
        
        # Build input 
        inp = build_input(target_fn_data, add_doc, add_ret_type)
        prompt = ""

        for i in range(len(examples)):
            # msg.append({"role": "user", "content": fs_examples[i][0]})
            # msg.append({"role": "assistant", "content": fs_examples[i][1]})

            # NOTE: The following method of adding all examples in on msg worked better
            #  than creating the whole conversation
            prompt += fs_examples[i][0] + fs_examples[i][1]
        
        full_prompt = prompt + inp
        
        if prev_result is not None:
            rep = "Your previous response:\n"
            rep += f"Postcondition:\n{prev_result['postcondition']}\n"
            rep += f"Error Type:\n{prev_result['result']}\n" 

            # If the error log is too long (more than 10 lines)
            # Extract lines that have error string in it
            error_summary = extract_error_lines(prev_result['error_output'])

            rep += f"Error log:{error_summary}\n\n" 
            rep += f"Your previous generation was buggy. Can you fix that error and generate a new postcondition?"
            full_prompt += rep
    else:
        # This is for nl2post prompt from the paper 
        # "Can LLMs Transform NL Intent into Formal Method Postconditions? FSE’24"
        # https://arxiv.org/pdf/2310.01831
        
        instruction = f"You have the following code context and natural language specification (in the form of code comment) for {target_fn_data.function_name}. The function should comply with natural language specification:\n"
        
        prompt = target_fn_data.function_string + post_prompt_instruction_nl2post.format(target_fn_data.function_name)

        for i in range(len(examples)):
            prompt += fs_examples[i][0] + fs_examples[i][1]

    # Apply chat template according to the tokenizer of the corresponding model
    if 'apply_chat_template' in dir(tokenizer):
        try:
            msg = [{"role": "system", "content": instruction}]
            msg.append({"role": "user", "content": full_prompt})
            chat_prompt = tokenizer.apply_chat_template(
                msg, 
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False
                )
        except jinja2.exceptions.TemplateError:
            # Some models do not support "system" message e.g. google/gemma-2-9b-it
            msg = [{"role": "user", "content": instruction+"\n"+full_prompt}]
            chat_prompt = tokenizer.apply_chat_template(
                msg, 
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False
                )
    else:
        raise ValueError("Not supported!")
    return chat_prompt

def build_input(target_fn_data, add_doc, add_ret_type):
    inp = f"Function:\n{target_fn_data.function_string}\n"

    if add_ret_type:
        rtype = target_fn_data.return_type.name
        inp += f"Return Type: {rtype}\n"
        inp += f"Arguments used for postcondition: res_tmp, {', '.join(target_fn_data.args)}\n"

    if add_doc:
        inp += f"Documentation:\n{target_fn_data.docstring}\n"
    return inp

def build_fewshot_example(add_doc, add_cot, add_ret_type, examples_dir, examples, i):
    fname = examples_dir+examples[i]['code_path']
    fnode = get_all_ts_function_nodes(fname)[0]
    docstring = get_ts_fn_node_docstring(fnode)
    fs_example = ""

    function_str = ''.join(common.get_file_lines(fname))

    # Create the part of the prompt with current example
    # prompt += f"\n------ Example {i+1}\n"

    # Add the function definition in the prompt
    fs_example += f"Function:\n{function_str}\n"

    cnode = get_all_functions_clang(fname)[-1]

    if add_ret_type:
        rtype = cnode.result_type.get_canonical().spelling
        fs_example += f"Return Type: {rtype}\n"
        fs_example += f"Arguments used for postcondition: res_tmp, {', '.join([arg.spelling for arg in cnode.get_arguments()])}\n"

    if add_doc: # Add documentation in the prompt
        fs_example += f"Documentation:\n{docstring}\n"

    fs_out = ""
    if add_cot:
        fs_out += f"Reasoning:\nLet's think about this step by step. {examples[i]['reasoning']}\n"

    fs_out += f"Postcondition:\n{examples[i]['post']}\n"
    return fs_example,fs_out

def extract_error_lines(text, max_lines=10):
    # Split the text into lines
    all_lines = text.splitlines()
    
    # If the entire text has fewer than 10 lines, return all lines
    if len(all_lines) <= max_lines:
        return text
    
    # Otherwise, extract lines containing "error" (case-insensitive)
    error_lines = [line for line in all_lines if "error" in line.lower()]
    
    # If there are more than max_lines error lines, return only the bottom max_lines
    if len(error_lines) > max_lines:
        error_lines = error_lines[-max_lines:]
    
    # Join the selected lines with newlines and return as a string
    return '\n'.join(error_lines)
    