# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Given a function, corresponding unit-test and proposed contract. Check if the assertion holds for tests.
"""
import re
import subprocess
import os
import common
from tester.contract_tester import ContractTester
from code_miner.ts_parser import get_all_ts_function_nodes
from typing import Iterator, Optional
from tree_sitter import Node
from common import get_file_lines, get_source_name
from pathlib import Path
from function_data import FunctionData, ReturnType

class BDETester(ContractTester):
    """
    Given a function in BDE with a corresponding postcondition, this class runs relevant unit tests to 
    check if the postcondition holds.
    """
    def __init__(self, root_dir, timeout=30, use_cache=False):
        # Copy the contents of repository to a temp path
        bash_command = f"rsync -avc {root_dir}/ analysis_code/tmp/{get_source_name(root_dir)} --exclude _build/"
        common.run_bash(bash_command, timeout=timeout)

        super().__init__(root_dir=root_dir, timeout=timeout, use_cache=use_cache)
    
    def _check_build(self):
        """
        Checks if the project builds without errors.
        """
        # Build BDE project and run the test target
        bash_command = f"cd {self.tmp_dir} && eval `bbs_build_env -u opt_64_cpp17` && bbs_build configure && bbs_build build --target help"
        output = common.run_bash(bash_command)

        if output is not None and output.returncode == 0:
            raw_output = output.stdout.decode('utf-8')
            # Regular expression to match filenames ending with ".t" 
            pattern = r'\b[\w\-\.]+\.t\b'  
            
            # Find all matches 
            targets = re.findall(pattern, raw_output)
            self.targets = [t[:-2] for t in targets] # Remove ".t"

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

    def check_assertion(self, fn: FunctionData, assertion: str) -> dict:
        """
        Let's say we want to check that postcondition assertion(1 > 0) holds at the end of the functions when the tests are run.
        The output is written to data/bde/result.jsonl file using `_write_result` function
        """
        cached_res = self._check_cache(fn.function_string, assertion)
        if cached_res != None:
            self._write_result(cached_res)
            return cached_res

        # Create a copy of the repository where the original function is replaced with function with an additional assertion
        bash_command = f"rsync -av {self.root_dir}/ analysis_code/tmp/{get_source_name(self.root_dir)} --exclude _build/"
        common.run_bash(bash_command)
        file_path = fn.file_path.replace(self.root_dir, self.tmp_dir)
        
        # Repleace the current function content with the addition of this assertion just before any return statement
        file_lines = get_file_lines(fn.file_path)
        
        # Start with original file content
        all_functions = get_all_ts_function_nodes(fn.file_path)

        # Create an empty file to write the results for CPP execution
        open(self._tmp_result_file, 'w+').close()
        
        # Find the function node in the tree-sitter AST that matches the offset of the function in the file  
        function_node = next(filter(lambda fn_node: fn_node.start_byte == fn.offset, all_functions), None)

        if function_node == None:
            return

        new_file_content = self._add_return_stub(assertion, file_lines, function_node, return_type=fn.return_type)

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

        # Aggregate the results from tmp file and store it in a `jsonl` with following format:
        return_code = output.returncode if output is not None else 1
        result = self._aggregate_results(fn, assertion, return_code, output_txt)
        return result


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

                # children are 1. "return" 2. expression 3. semicolon
                if len(cur_node.children) != 3:
                    print(f"Unexpected code at the return: {cur_node.text}")
                    continue
                
                start_line = cur_node.start_point.row
                end_line = cur_node.end_point.row

                original_context = ''.join(file_lines[start_line:end_line+1])

                return_str = cur_node.text.decode('utf-8')
                
                # Create the stub to replace the return statement
                # The stub does following operations in the C++ code
                # 1) Creates a temporary variable `res_tmp` and assigns it the return expression
                # 2) Prints function name, return value `res_tmp` and the validaty of the assertion
                # 3) Returns `res_tmp`
                return_expr = cur_node.children[1]
                return_expr_str = return_expr.text.decode('utf-8')

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


    def _run_ut(self, path: str) -> Optional[subprocess.Popen]:
        """
        Run unit test provided the path of the file to be tested or the test file itself. Given a file with path file.cpp,
        this function looks for the file file.t.cpp in same directory.
        """
        # Extract target from the path
        test_target = self._extract_target(path)
        
        # Find root of the target
        build_dir = None
        cur_dir = Path(path)
        while cur_dir != '':
            cur_dir = os.path.dirname(cur_dir)
            cmake_file = Path(cur_dir + '/project.cmake')
            if cmake_file.is_file():
                build_dir = cur_dir
                break
                
        if build_dir == None:
            raise ValueError("Build directory not found!")

        # Change directory to the target directory
        # Build BDE project and run the test target
        bash_command = f"cd {build_dir} && eval `bbs_build_env -u opt_64_cpp17` && bbs_build configure && bbs_build build --target {test_target} --test run"
        print(bash_command)
        return common.run_bash(bash_command)

    def _extract_target(self, path):
        if path.endswith('.t.cpp'):
            target = path.split('/')[-1][-5]
        elif path.endswith('.cpp'):
            target = path.split('/')[-1][:-4]
        else:
            raise ValueError('Unknown target!')
        return target

    def filter_fns_with_test_target(self, fns) -> Iterator[FunctionData]:
        filtered_fns = [fn for fn in fns if self._extract_target(fn.file_path) in self.targets]
        return filtered_fns
