# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import ast
from collections import defaultdict
import sys, os
from typing import Iterator
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'fun2spec'))
import common
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser
import statistics

def count_expression(assertion: str) -> bool:
    """
    Count number of valid atoms in the expression.
    """
    clean_post = assertion.replace(' ', '')
    if  clean_post in ['true', 'res_tmp!=NULL||res_tmp==NULL', 'res_tmp==NULL||res_tmp!=NULL', 'res_tmp==0||res_tmp!=0', 'res_tmp==0||res_tmp!=0', 'res_tmp==true||res_tmp==false', 'res_tmp==false||res_tmp==true']:
        return 1

    count = 1

    count += clean_post.count("&&") + clean_post.count("||") + clean_post.count("==>") 
    return count

def count_expression_size(model_name):
    count = 2000 
    return_type = 'all'
    gen_name = 'fun2spec'
    source = 'bde'

    # Load the json file with results
    log_path = f"{common.get_project_path()}/data/{common.get_source_name(source)}/{model_name}/"
    log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}"
    log_res_path = f"{log_path}/{log_file_name}.jsonl"

    # Store changes in a list
    file_lines = common.get_file_lines(log_res_path)
    freq = defaultdict(int) 

    for line in file_lines:
        data_dict = ast.literal_eval(line)

        if 'passed' not in data_dict or not data_dict['passed']: # Fail on a test
            continue
        
        cnt = count_expression(data_dict['postcondition'])
        freq[cnt] += 1

    avg = 0
    total = 0
    for k, v in freq.items():
        avg += k*v
        total += v

    print(f"Result for model: {model_name}")
    print(f"Frequency of number of atoms in the generated predicates: {sorted(dict(freq).items())}")
    print(f"Average size: {avg/total}")


def count_expression_size(model_name, source):
    count = 2000 
    return_type = 'all'
    gen_name = 'fun2spec'

    # Load the json file with results
    log_path = f"{common.get_project_path()}/data/{common.get_source_name(source)}/{model_name}/"
    log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}"
    # log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}_cot:False"
    # log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}_cot:True_ret:True_few_shot:0"
    log_res_path = f"{log_path}/{log_file_name}.jsonl"

    # Store changes in a list
    file_lines = common.get_file_lines(log_res_path)
    freq = defaultdict(int) 
    cnt_trivial = 0
    test_cnt = []
    cnt_expr_type = {'||': 0, "&&": 0, "==>": 0}
    has_expr_type = {'||': 0, "&&": 0, "==>": 0}
    cnt_all = 0

    for line in file_lines:
        data_dict = ast.literal_eval(line)

        if 'result' not in data_dict or data_dict['result'] != True: # Fail on a test
            continue

        clean_post: str = data_dict['postcondition'].replace(' ', '')
        if  clean_post in ['true', 'res_tmp!=NULL||res_tmp==NULL', 'res_tmp==NULL||res_tmp!=NULL', 'res_tmp==0||res_tmp!=0', 'res_tmp==0||res_tmp!=0', 'res_tmp==true||res_tmp==false', 'res_tmp==false||res_tmp==true']:
            cnt_trivial += 1
        
        cnt = count_expression(data_dict['postcondition'])
        freq[cnt] += 1
        test_cnt.append(data_dict['true']+data_dict['false'])
        cnt_all += 1
        for k in cnt_expr_type.keys():
            cnt_expr_type[k] += clean_post.count(k)
            has_expr_type[k] += (k in clean_post)

    avg = 0
    total = 0
    for k, v in freq.items():
        avg += k*v
        total += v

    print(f"Result for model, source: {model_name}, {source}")
    print(f"Trivial: {cnt_trivial}")
    print(f"Frequency of number of atoms in the generated predicates: {sorted(dict(freq).items())}")
    print(f"Average size: {avg/total}")
    print(f"Average tests: {statistics.median(test_cnt)}, {statistics.mean(test_cnt)}")
    # cnt_expr_type = {k:v/total for (k, v) in cnt_expr_type.items()}
    has_expr_type = {k:v/total for (k, v) in has_expr_type.items()}
    print(f"Count expression occ: {cnt_expr_type}")
    print(f"Has expression occ: {has_expr_type}")
    return test_cnt, has_expr_type, cnt_all

def type_analysis(model_name, source):
    count = 2000 
    return_type = 'all'
    gen_name = 'fun2spec'

    # Load the json file with results
    log_path = f"{common.get_project_path()}/data/{common.get_source_name(source)}/{model_name}/"
    log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}"
    # log_file_name = f"gen_name:{gen_name}_return_type:{return_type}_count:{count}_cot:{add_cot}_ret:{add_ret_type}"
    log_res_path = f"{log_path}/{log_file_name}.jsonl"

    # Store changes in a list
    file_lines = common.get_file_lines(log_res_path)
    freq = defaultdict(lambda: defaultdict(int))  
    
    
    for line in file_lines:
        data_dict = ast.literal_eval(line)

        if 'result' not in data_dict:
            continue

        freq[data_dict['return_type']][data_dict['result']] += 1

    for k, v in freq.items():
        print(k)
        print(v)


if __name__ == "__main__":
    models = ["Qwen/Qwen2.5-32B-Instruct", "Qwen/QwQ-32B-Preview", "Qwen/Qwen2.5-Coder-7B-Instruct", "meta-llama/Llama-3.1-8B-Instruct", "google/gemma-2-9b-it", "microsoft/phi-4", "microsoft/Phi-3.5-mini-instruct"]
    sources = ["bde", "bmq"]
    # models = ["Qwen/Qwen2.5-32B-Instruct"]
    test_cnt_all = []
    total_all = []
    has_expr_type_all = {'||': 0, "&&": 0, "==>": 0}
    all_cases = 0

    for source in sources:
        for model in models:
            all_cases += 1
            test_cnt, has_expr_type, total = count_expression_size(model, source)
            test_cnt_all += test_cnt
            
            for k in has_expr_type:
                has_expr_type_all[k] += has_expr_type[k]
            print(has_expr_type_all)
    
    for k in has_expr_type_all.keys():
        has_expr_type_all[k] /= all_cases
    print(has_expr_type_all)

    print(f"Average tests all: {statistics.median(test_cnt_all)}, {statistics.mean(test_cnt_all)}")
    # type_analysis("Qwen/Qwen2.5-32B-Instruct", source='bde')
