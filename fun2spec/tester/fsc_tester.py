# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import re
from function_data import FunctionData
from tester.contract_tester import ContractTester
from pathlib import Path
from datasets import load_dataset
import os, time, signal, subprocess, fcntl
import tempfile
from pathlib import Path

class FormalSpecCPPTester(ContractTester):
    """
    Given a function in HumanEval CPP dataset with a corresponding postcondition, this class runs relevant unit tests to 
    check if the postcondition holds.
    """
    def __init__(self, root_dir, **kwargs):
        kwargs['use_cache'] = False # testing is cheap we do not need to cache it
        super().__init__(root_dir=root_dir, **kwargs)
    
    def _check_build(self):
        """
        For FormalSpecCPP this should always be ok. 
        """
        pass

    def check_assertion(self, fn: FunctionData, assertion: str):
        """
        Tests if the given assertion holds true as a postcondition for the C++ code.

        function_string: The C++ function code.
        test_string: The C++ test code.
        assertion: The assertion to check (e.g., "res_tmp < 0").

        Returns:
        True if the assertion holds, False otherwise.
        """
        # with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as tmp_file:
        #     tmp_file.write(fn.function_string)
        #     function_file_path = tmp_file.name

        # Replace all the `return` expressions in the function with the stub that checks the 
        # postcondition as assertion
        tmp_var_string = r"{auto res_tmp = \g<1>;"
        create_file = f"std::ofstream f; f.open(std::string(\"{self._tmp_result_file}\"), std::ios::app); "
        new_code_stub = tmp_var_string + create_file + f"f << __FUNCTION__ << \" \" << ({assertion}) << std::endl; f.close(); return res_tmp;}}"

        function_string = re.sub(r'return(.*);', new_code_stub, fn.function_string)

        program = function_string + fn.test_string
        program = "#include <fstream>\n" + program

        with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False) as tmp_file:
            tmp_file.write(program)
            test_file_path = tmp_file.name

        res = ContractTester.eval_cpp_file(test_file_path)

        if res != None:
            output_txt = res['stdout'] + "\n" + res['stderr']
        else:
            output_txt = ""

        result = self._aggregate_results(fn, assertion, res['exit_code'], output_txt)
        return result

