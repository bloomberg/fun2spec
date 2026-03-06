# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Script to run all experiments
from main import run

def run_exp(reasoning_models, all_models, return_types, add_docs, add_cot, few_shots, use_quantifiers, reprompt, sources, timeout, count):
    for source in sources:
        for model in all_models:
            for few_shot in few_shots:
                for return_type in return_types:
                    for add_doc in add_docs:
                        if source == "humaneval":
                            add_ret_type = False
                        else:
                            add_ret_type = True


                        if model in reasoning_models:
                            max_new_tokens = 800
                        else:
                            max_new_tokens = 400

                        run(
                        source=source, 
                        model_name=model, 
                        return_type=return_type, 
                        use_cache=True, 
                        count=count, 
                        timeout=timeout, 
                        add_doc=add_doc, 
                        add_cot=add_cot,
                        few_shot=few_shot,
                        add_ret_type=add_ret_type,
                        use_quantifiers=use_quantifiers,
                        reprompt=reprompt,
                        max_new_tokens=max_new_tokens
                    )

def main():
    models = [
    "Qwen/Qwen3-32B",
    "Qwen/Qwen2.5-32B-Instruct",
    "Qwen/Qwen2.5-Coder-7B-Instruct", 
    "meta-llama/Llama-3.1-8B-Instruct", 
    "google/gemma-2-9b-it", 
    "microsoft/phi-4", 
    "microsoft/Phi-4-mini-instruct"
    ]

    reasoning_models = [
        "Qwen/QwQ-32B"
    ]

    all_models = models + reasoning_models

    # return_types = ['int', 'all']
    return_types = ['all']
    add_docs = [False]
    add_cot = True
    few_shots = [4]
    use_quantifiers = True
    reprompt = True

    # source = "humaneval"
    # source = "analysis_code/bde"
    sources = ["analysis_code/blazingmq"]
    # sources = ["humaneval", "analysis_code/bde", "analysis_code/blazingmq"]

    timeout = 60
    count = 1000
    run_exp(
        reasoning_models, 
        all_models, 
        return_types, 
        add_docs, 
        add_cot, 
        few_shots, 
        use_quantifiers, 
        reprompt,
        sources, 
        timeout, 
        count
        )

if __name__ == "__main__":
    main()
