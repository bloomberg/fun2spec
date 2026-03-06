# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import re
from function_data import FunctionData
from tester.contract_tester import ContractTester
from pathlib import Path
from datasets import load_dataset
import os, time, signal, subprocess, fcntl
import tempfile
from typing import Dict, List

class HumanEvalTester(ContractTester):
    """
    Given a function in HumanEval CPP dataset with a corresponding postcondition, this class runs relevant unit tests to 
    check if the postcondition holds.
    """
    def __init__(self, root_dir, **kwargs):
        kwargs['use_cache'] = False # Humaneval testing is cheap we do not need to cache it
        self.dataset = load_dataset("bigcode/humanevalpack", "cpp", trust_remote_code=True)["test"]
        super().__init__(root_dir=root_dir, **kwargs)

    def _check_build(self):
        """
        For HumanEval this should always be ok. 
        """
        pass

    def check_assertion(self, fn: FunctionData, assertion: str):
        """
        The output is written to data/humaneval/result.csv file
        """
        test_string = fn.test_string # This consists of all tests
        function_string = fn.function_string

        # Replace all the `return` expressions in the function with the stub that checks the 
        # postcondition as assertion
        # TODO: Refactor this into a method that can be used for all testers
        tmp_var_string = r"{auto res_tmp = \g<1>;"
        create_file = f"std::ofstream f; f.open(std::string(\"{self._tmp_result_file}\"), std::ios::app); "
        new_code_stub = tmp_var_string + create_file + f"f << __FUNCTION__ << \" \" << ({assertion}) << std::endl; f.close(); return res_tmp;}}"

        function_string = re.sub(r'return(.*);', new_code_stub, function_string)

        program = function_string + test_string
        program = "#include <fstream>\n" + program

        with tempfile.NamedTemporaryFile(suffix='.cpp', delete=True) as f:
            f.write(program.encode("utf-8"))
            f.flush()
            res = ContractTester.eval_cpp_file(Path(f.name))
        
        if res != None:
            output_txt = res['stdout'] + "\n" + res['stderr']
        else:
            output_txt = ""

        result = self._aggregate_results(fn, assertion, res['exit_code'], output_txt)
        return result
