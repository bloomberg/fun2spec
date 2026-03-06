# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
The main logic for generating contracts for functions using LLMs.
"""
import os, torch
import time
from typing import Iterator, Optional, Tuple, Union
from transformers import AutoModelForCausalLM, AutoTokenizer, StopStringCriteria, BitsAndBytesConfig
from transformers.utils import is_flash_attn_2_available
import common
from spec import Postcondition
from function_data import FunctionData
from llm_generator.prompt_builder import build_prompt
import code_miner.ts_parser as ts_parser
import logging
logger = logging.getLogger(__name__)

os.environ['CURL_CA_BUNDLE'] = ''
HF_ACCESS_TOKEN = os.environ['HF_ACCESS_TOKEN'] if 'HF_ACCESS_TOKEN' in os.environ else None

class FSGenerator:
    """
    This is the main class for fun2spec generator.
    """
    device: str
    model_name: str
    model: AutoModelForCausalLM
    tokenizer: AutoTokenizer

    def __init__(
            self, 
            model_name="microsoft/Phi-3-mini-128k-instruct", 
            device='cuda', 
            add_doc=False, 
            add_cot=True, 
            add_ret_type=True, 
            use_quantifiers=True, 
            few_shot=4, 
            quant_bits=None,
            max_new_tokens=400, 
            decode='greedy', 
            temperature=0.2,
            num_of_candidates=1,
            nl2post=False
            ):
        self.device = device
        self.model_name = model_name
        self.num_of_candidates = num_of_candidates
        self.nl2post = nl2post

        torch.random.manual_seed(0)

        if quant_bits == 4:
            q_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
            torch_dtype="auto"
        elif quant_bits == 8:
            q_config = BitsAndBytesConfig(load_in_8bit=True, bnb_4bit_compute_dtype=torch.bfloat16)
            torch_dtype="auto"
        else:
            torch_dtype=torch.bfloat16
            q_config = None

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            device_map="cuda", 
            torch_dtype=torch_dtype, 
            quantization_config=q_config,
            attn_implementation="flash_attention_2" if is_flash_attn_2_available() else None, 
            token=HF_ACCESS_TOKEN,
            trust_remote_code=True
        ).eval()

        self.tokenizer = AutoTokenizer.from_pretrained(model_name, token=HF_ACCESS_TOKEN)
        self.add_doc = add_doc
        self.add_cot = add_cot
        self.add_ret_type = add_ret_type
        self.few_shot = few_shot
        self.use_quantifiers = use_quantifiers

        # self.pipe = pipeline("text-generation", model=self.model, tokenizer=self.tokenizer)

        if decode == 'greedy':
            self.generation_args = {
                "max_new_tokens": max_new_tokens,
                "num_return_sequences": num_of_candidates,
                "output_scores": True,
                "return_dict_in_generate": True,
                "stopping_criteria": [StopStringCriteria(tokenizer=self.tokenizer, stop_strings=['-----'])]
            }
        elif decode == 'sample':
            self.generation_args = {
                "max_new_tokens": max_new_tokens,
                "do_sample": True,
                "temperature": temperature,
                'num_return_sequences': num_of_candidates,
                "output_scores": True,
                "return_dict_in_generate": True,
                "stopping_criteria": [StopStringCriteria(tokenizer=self.tokenizer, stop_strings=['-----'])]  # TODO: this doesn't seem to work
            }
        elif decode == 'diverse_beam':
            self.generation_args = {
                "max_new_tokens": max_new_tokens,
                "num_beams": num_of_candidates,
                "num_beam_groups": num_of_candidates,
                "diversity_penalty": 0.,
                'num_return_sequences': num_of_candidates,
                "output_scores": True,
                "return_dict_in_generate": True,
                "stopping_criteria": [StopStringCriteria(tokenizer=self.tokenizer, stop_strings=['-----'])]  # TODO: this doesn't seem to work
            }

    def get_candidate_outputs(self, prompts: Iterator[str]) -> Iterator[Optional[Iterator[Tuple[str, float]]]]:
        """
        Returns a list of pairs of output text and confidence scores -> (output, scores)
        """
        try:
            input_batch = prompts # Multiple prompts in a batch
            batch_size = len(prompts)

            self.tokenizer.pad_token = self.tokenizer.eos_token
            inputs = self.tokenizer(input_batch, return_tensors="pt", padding=True).to(self.model.device)

            start_time = time.time()
            llm_output = self.model.generate(
                **inputs, 
                **self.generation_args
                )
            
            num_of_tokens = llm_output['sequences'].numel()-inputs['input_ids'].numel()
            logger.info(f"Number of tokens generated: {num_of_tokens}")
            logger.info(f"Inference speed: {num_of_tokens/(time.time()-start_time):.2f} tok/sec")
            generated_strs = self.tokenizer.batch_decode(llm_output['sequences'], skip_special_tokens=False)

            # "num_of_candidates" of outputs for each prompt
            outputs = []
            for i in range(batch_size):
                output_i = []
                for j in range(self.num_of_candidates):
                    out_str = generated_strs[i][len(prompts[i]):]
                    score = llm_output['sequences_scores'][i].item() if 'sequences_scores' in llm_output.keys() else 0
                    
                    output_i.append((out_str, score))
                outputs.append(output_i) 
        except torch.cuda.OutOfMemoryError:
            print('Failed due to CUDA out of memory!')
            outputs = None

        # Clear CUDA cache
        torch.cuda.empty_cache()

        return outputs


    def get_postcondition(
            self, 
            fn_datas:Iterator[FunctionData],
            prev_result:dict=None 
            ) -> Union[Optional[Postcondition], str]:
        """
        Returns a postocondition string if the LLM generated string can be parsed to extract the postcondition in exprected format.
        Returns None otherwise.
        """
        prompts = []
        batch_size = len(fn_datas)

        for fn_data in fn_datas:
            prompt = build_prompt(
                fn_data, 
                self.tokenizer,
                add_doc=self.add_doc, 
                add_cot=self.add_cot, 
                add_ret_type=self.add_ret_type, 
                few_shot=self.few_shot, 
                quantifier_prompt=self.use_quantifiers,
                prev_result=prev_result,
                nl2post=self.nl2post
                )        
            prompts.append(prompt)

        # Make the LLM call and get the candidate postconditions
        raw_candidates = self.get_candidate_outputs(prompts)
        
        chos_cands_list = []

        for idx in range(batch_size):
            chosen_candidate = None
            best_prob = -float("inf")
            raw_candidate = raw_candidates[idx]

            if raw_candidate == None:
                chos_cands_list.append((None, raw_candidates))
                continue

            candidates = [Postcondition(predicate=common.extract_predicate(cd[0]), reasoning=common.extract_reasoning(cd[0]), prob=cd[1]) 
                            for cd in raw_candidate]

            # Choose the candidate postcondition that is valid and has the highest probability according to the LLM
            for ps in candidates:
                try:
                    inp_symbols = fn_data.args + ['res_tmp']
                    is_valid = ts_parser.validate_expression(ps.predicate, inp_symbols)

                    if ps.prob > best_prob and is_valid:
                        chosen_candidate = ps
                        best_prob = ps.prob
                except:
                    print(f"Parsing of following the LLM output failed:\n{ps.predicate}")

            # All candidates fail the valid check just return the first one for now
            # TODO: make this return None when we have enough confidence on the `validate_expression` check
            if chosen_candidate == None:
                chos_cands_list.append((candidates[0], raw_candidate)) 
                continue

            # Print candidates and chosen candidate
            chos_cands_list.append((chosen_candidate, raw_candidates)) 

        return chos_cands_list
    