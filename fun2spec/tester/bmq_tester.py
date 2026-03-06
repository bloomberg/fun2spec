# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import subprocess
import common
from tester.contract_tester import ContractTester
from code_miner.ts_parser import get_all_ts_function_nodes
from typing import Iterator, Optional
from tree_sitter import Node
from common import get_file_lines, get_source_name
from pathlib import Path
from function_data import FunctionData, ReturnType

class BMQTester(ContractTester):
    """
    Given a function in BlazingMQ with a corresponding postcondition, this class runs relevant unit tests to 
    check if the postcondition holds.
    """
    def __init__(self, root_dir, timeout=30, use_cache=True):
        # Copy the contents of repository to a temp path
        bash_command = f"rsync -avc {root_dir}/ analysis_code/tmp/{get_source_name(root_dir)} --exclude build/blazingmq"
        common.run_bash(bash_command, timeout=timeout)

        super().__init__(root_dir=root_dir, timeout=timeout, use_cache=use_cache)

    def _check_build(self):
        """
        Checks if the project builds without errors.
        """
        # Build BMQ project
        bash_command = f"cd {self.tmp_dir} && bin/build-ubuntu.sh && cmake --build build/blazingmq --parallel 8 --target all.t"
        output = common.run_bash(bash_command, timeout=200)
    
        if output is not None and output.returncode == 0:
            print('Build tested!')
        else:
            if output is not None:
                print(f"Build failed with Error code {output.returncode}!")
                print(output.returncode)
                print(output.stdout.decode('utf-8'))
                print(output.stderr.decode('utf-8'))
            else:
                print(f"Build failed and the output is None!")
            raise Exception('Build Failed!')
    
    def check_assertion(self, fn: FunctionData, assertion: str):
        """
        Checks if the `assertion` holds at the end of the function execution.
        The output is written to data/bmq/result.csv file using `_write_result` function
        """
        # cached_res = self._check_cache(fn.function_string, assertion)
        # if cached_res != None:
        #     self._write_result(cached_res)
        #     return cached_res

        # Create a copy of the repository where the original function is replaced with function with an additional assertion
        bash_command = f"rsync -av {self.root_dir}/ analysis_code/tmp/{get_source_name(self.root_dir)} --exclude build/blazingmq"
        common.run_bash(bash_command)
        file_path = fn.file_path.replace(self.root_dir, self.tmp_dir)
        
        # Repleace the current function content with the addition of this assertion just before any return statement
        file_lines = get_file_lines(fn.file_path)
        
        # Start with original file content
        new_file_content = ''.join(file_lines) 
        all_functions = get_all_ts_function_nodes(fn.file_path)

        # Create an empty file to write the results for CPP execution
        open(self._tmp_result_file, 'w+').close()
        
        # Find the function node in the tree-sitter AST that matches the offset of the function in the file  
        function_node = next(filter(lambda fn_node: fn_node.start_byte == fn.offset, all_functions), None)

        if function_node == None:
            return

        new_file_content = self._add_return_stub(assertion, file_lines, function_node, fn.return_type)

        # replce the file_content with new_file_content
        print(f"Rewriting the function {fn.function_name} in temporary file {file_path}")
        # Add header for writing to a file
        self._add_fstream_header(file_path, new_file_content)
        
        # Run unit test for the target file
        output = self._run_ut(file_path)
        if output != None:
            output_txt = output.stdout.decode('utf-8') + "\n" + output.stderr.decode('utf-8')
        else:
            output_txt = ""

        if output is not None and output.returncode == 0:
            print('Test executed!')
        else:
            if output is not None:
                print(f"Test execution failed with Error code {output.returncode}!")
                print(output.returncode)
                print(output_txt)
            else:
                print(f"Test failed and the output is None!")

        # Aggregate the results from tmp file and store it in a jsonl with following format:
        return_code = output.returncode if output is not None else 1
        result = self._aggregate_results(fn, assertion, return_code, output_txt)
        return result

    def _run_ut(self, path: str) -> Optional[subprocess.Popen]:
        """
        Run unit test provided the path of the file to be tested or the test file itself. Given a file with path file.cpp,
        this function looks for the file file.t.cpp in same directory.
        """
        # Change location to BMQ build directory
        build_dir = "build/blazingmq"

        # Run ctest with -R
        test_file = path.split('/')[-1][:-4]
        return common.run_bash(f"cd {self.tmp_dir} && bin/build-ubuntu.sh && cmake --build build/blazingmq --parallel 8 --target all.t && cd {build_dir} && ctest -R {test_file}", timeout=200)


    def _add_fstream_header(self, file_path, new_file_content):
        new_file_content = '#include <bsl_fstream.h>\n' + new_file_content 
        with open(file_path, "w") as f:
            f.write(new_file_content)

    def _add_return_stub(self, assertion: str, file_lines: Iterator[str], function_node: Node, return_type:ReturnType=None):
        """
        Given file content split into lines `file_lines` and a tree-sitter function node, find and replace all occurences of return statements with a corresponding print stub.
        """
        worklist: Iterator[Node] = function_node.children
        new_file_content = ''.join(file_lines)  # Start with original file content
        
        # Do a BFS of the AST and find the return nodes 
        while len(worklist) > 0:
            cur_node = worklist.pop()

            if cur_node.type == 'return_statement':
                assert len(cur_node.children) == 3 # children are 1. "return" 2. expression 3. semicolon
                start_line = cur_node.start_point.row
                end_line = cur_node.end_point.row

                original_context = ''.join(file_lines[start_line:end_line+1])

                return_str = cur_node.text.decode('utf-8')
                
                # Create the stub to replace the return statement
                # The stub does following operations in the C++ code
                # 1) Creates a temporary variable `res_tmp` and assigns it the return expression
                # 2) Prints function name, return value `res_tmp` and the validaty of the assertion
                # 3) Returns `res_tmp`
                return_expr_str = cur_node.children[1].text.decode('utf-8')
                # tmp_var_string = f"auto res_tmp = {return_expr_str};"
                tmp_var_string = self._get_res_tmp_assignment(return_type, return_expr_str)

                create_file = f"std::ofstream f; f.open(std::string(\"{self._tmp_result_file}\"), std::ios::app); "
                new_code_stub = tmp_var_string + create_file + f"f << __FUNCTION__ << \" \" << ({assertion}) << \"\\n\"; f.close(); BSLS_ASSERT({assertion}); return res_tmp;"
                
                new_context = original_context.replace(return_str, f"BSLS_ASSERT({assertion}); {return_str}")
                new_context = original_context.replace(return_str, new_code_stub)

                new_file_content = ''.join(file_lines[:start_line] + [new_context] + file_lines[end_line+1:])
                file_lines = new_file_content.splitlines(keepends=True) # Update file lines
            else:
                worklist += cur_node.children
        return new_file_content