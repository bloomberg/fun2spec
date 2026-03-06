# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Given a function, corresponding unit-test and proposed contract. Check if the assertion holds for tests.
"""
import os
import pickle
import common
from typing import List, Optional
from pathlib import Path
from function_data import FunctionData
from abc import abstractmethod
from collections import defaultdict
from common import get_file_lines
from function_data import FunctionData
from pathlib import Path
import os, time, signal, subprocess, fcntl
from typing import Dict, List


class ContractTester:
    """
    Base class for contract testing module. 
    """
    def __init__(self, root_dir, timeout=30, use_cache=True):
        self.root_dir = root_dir
        self._timeout = timeout
        self.tmp_dir = 'analysis_code/tmp/' + common.get_source_name(root_dir)
        self._use_cache = use_cache
        Path(self.tmp_dir).mkdir(parents=True, exist_ok=True)
        self._tmp_result_file = f"{common.get_project_path()}/data/{common.get_source_name(root_dir)}/tmp.txt"
        with open(self._tmp_result_file, 'w') as f: f.write('') # Create an empty file

        self._result_cache_file = None
        # Check if the build of the project works
        self._check_build()

        # Cache for test results
        self._result_cache_file = "data/test_result_cache.pkl"
        self._result_cache: map[int, str] = self._load_cache()
        self._result_file = f"{common.get_project_path()}/data/{common.get_source_name(root_dir)}/function_result.jsonl"

        with open(self._result_file, 'w') as f: f.write('') # Create an empty file
        

    @abstractmethod
    def _check_build(self):
        """
        Checks if the project builds without errors.
        """
        pass

    @abstractmethod
    def check_assertion(self, fn: FunctionData, assertion: str):
        """
        Let's say we want to check that postcondition assertion(1 > 0) holds at the end of the functions when the tests are run
        """
        pass
    
    def _get_res_tmp_assignment(self, return_type, return_expr_str):
        if "int" in return_type.name:
            if return_type.name.strip() == 'int':
                        # NOTE:
                        # Clang uses `int` as default type on any error in inferring the return type of a function. In these cases,
                        # relying on auto types is more likely to compile. 
                tmp_var_string = f"auto res_tmp = {return_expr_str};"
            elif return_type.name.strip() == 'int&': 
                tmp_var_string = f"auto res_tmp = &{return_expr_str};"
            else:
                tmp_var_string = f"auto res_tmp = {return_expr_str};"
        else:
            tmp_var_string = f"{return_type.name} res_tmp = {return_expr_str};"
        return tmp_var_string
    
    def _aggregate_results(self, fn: FunctionData, assertion: str, test_return_code:int, output_txt: str) -> dict:
        agg_res = defaultdict(int)
        try:
            for res_line in get_file_lines(self._tmp_result_file):
                tr = res_line.split(' ')
                fname, predicate_val = tr[0], int(tr[1])
                agg_res[(fname, predicate_val)] += 1
        except:
            # TODO: Remove this in future. There may be issues where (fname, output_val, predicate_val) are not parsed correctly since 
            # LLM output could be arbitraty. 
            pass 
        
        count_true = agg_res[(fn.function_name, 1)]
        count_false = agg_res[(fn.function_name, 0)]
        clean_asserion = assertion.replace("'", "`").replace('"', "`")

        if count_true > 0 and count_false == 0:
            res_status = True
        elif "error: invalid conversion from" in output_txt or "local variable ‘res_tmp’ returned" in output_txt:
            # NOTE: This is most likely due to error in Clang parsing the return type
            # We will exclude these cases from evaluation
            res_status = "Clang Error"
        elif count_false > 0:
            res_status = False
        elif count_true == 0 and count_false == 0:
            if test_return_code == 0:
                res_status = "No test"
            else:
                res_status = "Compilation error"
        else:
            print(count_true, count_false)
            res_status = "No test"
            print("Unexpected scenario!")

        result = {
            "result": res_status,
            "function name": fn.function_name, 
            "true": count_true, 
            "false": count_false, 
            "return_code": test_return_code, 
            "file": fn.file_path, 
            "cpp_post": clean_asserion, 
            "offset":fn.offset,
            "return_type": fn.return_type.category.spelling,
            "error_output": output_txt
        }        
        self._write_result(result)

        if test_return_code == 0:
            # Cache only when the compilation guaranteed to not timed out
            self._add_cache(fn.function_string, assertion, result)

        return result

    def _write_result(self, result: dict):
        with open(self._result_file, 'a') as f: 
            f.write(str(result) + '\n')

    def _load_cache(self) -> map:
        if os.path.isfile(self._result_cache_file):
            with open(self._result_cache_file, 'rb') as fp:
                return pickle.load(fp)
        return {}
    
    def _store_cache(self):
        with open(self._result_cache_file, 'wb') as fp:
            pickle.dump(self._result_cache, fp) 

    def _check_cache(self, fn_string: str, assertion: str) -> Optional[str]:
        """
        We cache the results for checking assertion for faster testing.
        TODO: The cache currently does not account for change in test files. Fix this!
        """
        hs = common.persistent_hash(fn_string+assertion)
        if self._use_cache and hs in self._result_cache:
            return self._result_cache[hs]
        return None

    def _add_cache(self, fn_string: str, assertion: str, result: str) -> Optional[str]:
        hs = common.persistent_hash(fn_string+assertion)
        self._result_cache[hs] = result

    def __del__(self):
        if self._result_cache_file is not None: 
            print(f"Storing the updated cache at {self._result_cache_file}.")
            self._store_cache()

    @staticmethod
    def eval_cpp_file(path: Path) -> Dict:
        basename = ".".join(str(path).split(".")[:-1])
        build_result = ContractTester.run(["g++", path, "-o", basename, "-std=c++17"])
        if build_result.exit_code != 0:
            print("Compilation failed!")
            print(build_result.stderr)
            return {
                "status": "SyntaxError",
                "exit_code": build_result.exit_code,
                "stdout": build_result.stdout,
                "stderr": build_result.stderr,
            }

        run_result = ContractTester.run([basename])
        if "/4.8.2" in run_result.stderr:
            raise Exception("Ancient compiler encountered")
        if run_result.timeout:
            status = "Timeout"
        elif run_result.exit_code != 0:
            status = "Exception"
        else:
            status = "OK"
        return {
            "status": status,
            "exit_code": run_result.exit_code,
            "stdout": run_result.stdout,
            "stderr": run_result.stderr,
        }

    class Result:
        timeout: int
        exit_code: int
        stdout: str
        stderr: str

        def __init__(self, timeout, exit_code, stdout, stderr):
            self.timeout = timeout
            self.exit_code = exit_code
            self.stdout = stdout
            self.stderr = stderr

    @staticmethod
    def run(
        args: List[str],
        timeout_seconds: int = 15,
        max_output_size: int = 2048,
        env=None,
    ) -> Result:
        """
        Runs the given program with arguments. After the timeout elapses, kills the process
        and all other processes in the process group. Captures at most max_output_size bytes
        of stdout and stderr each, and discards any output beyond that.
        """
        MAX_BYTES_PER_READ = 1024
        def set_nonblocking(reader):
            fd = reader.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        p = subprocess.Popen(
            args,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=MAX_BYTES_PER_READ,
        )
        set_nonblocking(p.stdout)
        set_nonblocking(p.stderr)

        process_group_id = os.getpgid(p.pid)

        # We sleep for 0.1 seconds in each iteration.
        max_iterations = timeout_seconds * 10
        stdout_saved_bytes = []
        stderr_saved_bytes = []
        stdout_bytes_read = 0
        stderr_bytes_read = 0
        SLEEP_BETWEEN_READS = 0.1

        for _ in range(max_iterations):
            this_stdout_read = p.stdout.read(MAX_BYTES_PER_READ)
            this_stderr_read = p.stderr.read(MAX_BYTES_PER_READ)
            # this_stdout_read and this_stderr_read may be None if stdout or stderr
            # are closed. Without these checks, test_close_output fails.
            if this_stdout_read is not None and stdout_bytes_read < max_output_size:
                stdout_saved_bytes.append(this_stdout_read)
                stdout_bytes_read += len(this_stdout_read)
            if this_stderr_read is not None and stderr_bytes_read < max_output_size:
                stderr_saved_bytes.append(this_stderr_read)
                stderr_bytes_read += len(this_stderr_read)
            exit_code = p.poll()
            if exit_code is not None:
                break
            time.sleep(SLEEP_BETWEEN_READS)

        try:
            # Kills the process group. Without this line, test_fork_once fails.
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass

        timeout = exit_code is None
        exit_code = exit_code if exit_code is not None else -1
        stdout = b"".join(stdout_saved_bytes).decode("utf-8", errors="ignore")
        stderr = b"".join(stderr_saved_bytes).decode("utf-8", errors="ignore")
        return ContractTester.Result(timeout=timeout, exit_code=exit_code, stdout=stdout, stderr=stderr)
    

class FileTester(ContractTester):
    """
    We do not have a way to test a standalone cpp file provided for generating postcondition without any unit tests.   
    """
    def __init__(self, root_dir, timeout=30):
        pass

    def _check_build(self):
        """
        Do nothing
        """
        pass

    @abstractmethod
    def check_assertion(self, fn: FunctionData, assertion: str):
        """
        Do nothing
        """
    
    def __del__(self):
        pass
    