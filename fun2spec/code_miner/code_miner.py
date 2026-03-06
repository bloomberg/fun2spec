# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
This file contains code for parsing the C++ files in a specified repository and collect relevant function level
data that is used as test set for contract generation.
"""
from abc import abstractmethod
import os, pickle
import re
import common
from typing import Iterator
from tree_sitter import Node
from code_miner.ts_parser import get_all_ts_function_nodes, get_function_name, get_ts_fn_node_docstring
from pathlib import Path
from collections import defaultdict
from code_miner.clang_parser import get_all_functions_clang, get_docstring_from_headers
from clang.cindex import TypeKind
from function_data import ReturnType, FunctionData
from tqdm import tqdm


class CodeMiner:
    """
    This is a base class for analyzing code in repositories that needs to be overlloaded for specific type of repositories.

    Attributes
    ----------
    fns: List of function data extracted from analyzing the provided repository.
    """
    fns: Iterator[FunctionData]

    def __init__(self, source, use_cache=True):
        cache_path = f"{common.get_project_path()}/data/{common.get_source_name(source)}/function_data.pkl"

        if use_cache and os.path.isfile(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    self.fns = pickle.load(f)
                return
            except:
                pass
        
        # If cache is not available analyze the repository and cache the results for future use
        print('The cache is not used or available. Analyzing the source.')
        self.fns = self._analyze_source(source)
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'wb') as f:
            pickle.dump(self.fns, f)

    @staticmethod
    @abstractmethod
    def _analyze_source(path) -> Iterator[FunctionData]:
        pass

    def filter_by_return_type(self, return_type:str|list ='int', with_docstring=True) -> Iterator[FunctionData]:
        if with_docstring:
            fns = [fn for fn in self.fns if len(fn.docstring) > 0]
        else:
            fns = self.fns

        # Filter functions returning void
        fns = [fn for fn in fns if fn.return_type.category.value != TypeKind.VOID.value]
        
        if return_type == 'all':
            return fns

        if type(return_type) == str: # Create a list of single string in this case
            return_type = [return_type]

        # The type matching is using the value - TypeKind.value
        # TODO: Merge multiple similar types in one (e.g. FLOAT, DOUBLE, FLOAT128)
        type_name_to_kind = {'int': TypeKind.INT, 'pointer': TypeKind.POINTER, 'float': TypeKind.FLOAT}

        assert all(rt in type_name_to_kind for rt in return_type), f"Provided return type {return_type} is not supported!"

        return_type_kinds = [type_name_to_kind[rt].value for rt in return_type]
        filtered_fns = [fn for fn in fns if fn.return_type.category.value in return_type_kinds]
        return list(filtered_fns)

    @staticmethod
    def create_function_data(file_path, ts_fn_node, clang_fn_node, docstring='') -> FunctionData:
        """
        Creates and returns a FunctionData object given corresponding tree-sitter and clang nodes.
        """
        clang_return_type = clang_fn_node.result_type.get_canonical()
        return_type = ReturnType(clang_return_type.spelling, category=clang_return_type.kind)
        
        # from clang.cindex import TypeKind
        function_name = clang_fn_node.spelling
        args = [arg.spelling for arg in clang_fn_node.get_arguments()]

        return FunctionData(
                    function_name=function_name, 
                    file_path=str(file_path), 
                    function_string=ts_fn_node.text.decode("utf-8"), 
                    return_type=return_type, 
                    docstring=docstring,
                    offset=ts_fn_node.start_byte,
                    args=args
                    )

class HumanEvalMiner(CodeMiner):
    """
    This implementation of miner is responsible for analyzing CPP functions in the HumanEval-CPP dataset
    https://huggingface.co/datasets/THUDM/humaneval-x
    """
    def __init__(self, source, use_cache=True):
        super().__init__(source, use_cache)

    @staticmethod
    def _analyze_source(path) -> Iterator[FunctionData]:
        # Load the humaneval CPP dataset
        from datasets import load_dataset
        ds = load_dataset("bigcode/humanevalpack", "cpp", trust_remote_code=True)["test"]
        fns = []
        
        file_store_dir = f"{common.get_project_path()}/data/{common.SourceType.humaneval}/files/"
        Path(file_store_dir).mkdir(parents=True, exist_ok=True)

        for idx in range(len(ds)):
            file_path = f"{file_store_dir}cpp{idx}.cpp"

            function_string = ds[idx]['prompt'] + ds[idx]['canonical_solution']
            test_string = ds[idx]['test']

            # There is a bug in the dataset
            # Created a PR for this upstream on the dataset to fix this https://huggingface.co/datasets/bigcode/humanevalpack/discussions/5
            # For now, just manually fix it here
            if idx == 121:
                test_string = test_string.replace('solutions(', 'solution(')
                function_string = function_string.replace('solutions(', 'solution(')
            elif idx == 156:
                test_string = test_string.replace('int_to_mini_romank(', 'int_to_mini_roman(')  
                function_string = function_string.replace('int_to_mini_romank(', 'int_to_mini_roman(')          

            with open(file_path, '+w') as f:
                f.write(function_string+test_string)
                f.flush()
            
            # Clag also parses all functions in the header files. Thus we need to find the function of interest
            clang_fn_node = None

            for cnode in get_all_functions_clang(file_path):
                if cnode.spelling == ds[idx]['entry_point']:
                    clang_fn_node = cnode
            
            assert clang_fn_node is not None, idx

            try:
                docstring = re.search(r"\/\*((.|\n)*)\*\/", function_string+test_string).group(0)[2:-2].lstrip('\n').rstrip('\n')
            except:
                print(f"For HumanEval example {idx} - docstring not found!")
                docstring = ""

            offset = clang_fn_node.extent.start.offset
            return_type = ReturnType(clang_fn_node.result_type.get_canonical().spelling, category=clang_fn_node.result_type.get_canonical().kind)
            function_name = clang_fn_node.spelling
            args = [arg.spelling for arg in clang_fn_node.get_arguments()]

            fnd = FunctionData(
                function_name, 
                file_path, 
                function_string, 
                offset, 
                return_type=return_type, 
                docstring=docstring, 
                idx=idx, 
                args=args,
                test_string=test_string
                )
            fns.append(fnd)

        return fns

class FormalSpecCPPMiner(CodeMiner):
    """
    This implementation of miner is responsible for analyzing CPP functions in 
    https://github.com/MadhuNimmo/FormalSpecCpp
    """
    def __init__(self, source, use_cache=True):
        super().__init__(source, use_cache)
    
    @staticmethod
    def _analyze_source(path) -> Iterator[FunctionData]:
        cur_dir = os.path.abspath(os.path.dirname(__file__))

        # FormalSpecCPP  FormalSpecCPP-NoSpec  FormalSpecCPP-Tests
        data_dir = os.path.join(cur_dir, "../../data/FormalSpecCpp-Dataset")
        test_dir = os.path.join(data_dir, "FormalSpecCPP-Tests")
        spec_dir = os.path.join(data_dir, "FormalSpecCPP")
        nospec_dir = os.path.join(data_dir, "FormalSpecCPP-NoSpec")

        fns = []
        file_store_dir = f"{common.get_project_path()}/data/{common.SourceType.FSC}/files/"
        Path(file_store_dir).mkdir(parents=True, exist_ok=True)

        # Iterate over all .cpp files in the directory
        for file in list(Path(spec_dir).rglob("*.cpp")):
            filename = os.path.split(file)[1]
            base_name = os.path.splitext(filename)[0]
            new_file_path = f"{file_store_dir}{base_name}.cpp"
            
            # Function string (remove all postconditions)
            function_string = "".join(common.get_file_lines(file))
            gt_posts = re.findall(r'ENSURE\((.*?)\);', function_string) # Ground Truth
            function_string = re.sub(r'^\s*ENSURE\(.*\);\s*$', '', function_string, flags=re.MULTILINE)
            function_string = re.sub(r'^\s*//\s*Postcondition.*$', '', function_string, flags=re.MULTILINE)

            # Test string           
            test_file = os.path.join(test_dir, f"{base_name}_test.cpp")
            test_string = "".join(common.get_file_lines(test_file)[1:])

            # Clag also parses all functions in the header files. Thus we need to find the function of interest
            clang_fn_node = None
            clang_fn_node = get_all_functions_clang(file)[-1]
            
            offset = clang_fn_node.extent.start.offset
            return_type = ReturnType(clang_fn_node.result_type.get_canonical().spelling, category=clang_fn_node.result_type.get_canonical().kind)
            function_name = clang_fn_node.spelling
            args = [arg.spelling for arg in clang_fn_node.get_arguments()]

            fnd = FunctionData(
                function_name, 
                None, 
                function_string, 
                offset, 
                return_type=return_type, 
                args=args,
                test_string=test_string,
                ground_truth=gt_posts
                )
            fns.append(fnd)

        return fns


class FileMiner(CodeMiner):
    """
    This implementation of miner is responsible for analyzing single CPP file. 
    """
    def __init__(self, source, use_cache=False):
        # Do not use cache for single file since it is cheap
        super().__init__(source, use_cache=False)

    @staticmethod
    def _analyze_source(file_path: str) -> Iterator[FunctionData]:
        # ts_fn_nodes is a list of tree-sitter function nodes in the given file
        ts_fn_nodes: Iterator[Node] = get_all_ts_function_nodes(file_path) 

        clang_fn_nodes = get_all_functions_clang(file_path)
        offset_to_clang_node_map = {clang_fn_node.extent.start.offset: clang_fn_node for clang_fn_node in clang_fn_nodes}

        fns = []

        # Analyze each function in the file
        for ts_fn_node in ts_fn_nodes:
            assert ts_fn_node.type == 'function_definition'
                            
            if ts_fn_node.start_byte not in offset_to_clang_node_map:
                # In many cases clang would filter functions that are under "#ifdef" directive where the 
                # corresponding macro is not defined
                continue
            
            clang_fn_node = offset_to_clang_node_map[ts_fn_node.start_byte]
            function_data = CodeMiner.create_function_data(file_path, ts_fn_node, clang_fn_node)
            fns.append(function_data)

        return fns

class BDEMiner(CodeMiner):
    """
    This implementation of miner makes specific assumptions that hold for Bloomberg's BDE repository 
    https://github.com/bloomberg/bde
    """
    def __init__(self, source, use_cache=True):
        super().__init__(source, use_cache)

    def _get_targets(self):
        """
        Extract all cmake targets. This is a good approximation to finding functions that have corresponding unit tests. 

        TODO: It is unclear why some test files such as balst_assertionlogger.t exist but they are not a cmake target.
        Figure out why.
        """

    @staticmethod
    def _analyze_source(path) -> Iterator[FunctionData]:
        """
        Recursively analyze all cpp files in directory at this path and its subdirectories 
        """
        cpp_files = list(Path(path).rglob("*.cpp"))
        count_cpp_files = 0
        count_cpp_files_with_tests = 0
        count_functions_with_tests = 0
        count_functions_with_docstrings = 0
        fns: Iterator[FunctionData] = []
        pbar = tqdm(total=len(cpp_files))

        for file_path in cpp_files:
            pbar.update(1)
            if str(file_path).endswith('.t.cpp'):
                continue
            
            # Check if the corresponding test file exists
            test_file = Path(str(file_path).replace('cpp', 't.cpp'))
            if not test_file.is_file():
                continue

            # ts_fn_nodes is a list of tree-sitter function nodes in the given file
            ts_fn_nodes: Iterator[Node] = get_all_ts_function_nodes(str(file_path)) 

            function_node_to_name = {function_node: get_function_name(function_node) for function_node in ts_fn_nodes}
            named_functions = [function_name for _, function_name in function_node_to_name.items() if function_name is not None]

            # Create a local call graph within the given file
            call_graph = BDEMiner._get_call_graph(ts_fn_nodes, function_node_to_name, named_functions)

            # Create a calls relation 
            transitive_calls_relation = BDEMiner._get_calls_relations(ts_fn_nodes, function_node_to_name, call_graph)

            count_cpp_files += 1
            
            # A map from function to list of test functions that it calls
            tests = BDEMiner._get_test_map(count_cpp_files_with_tests, named_functions, transitive_calls_relation, test_file)

            # Get the map of clang nodes for each functions as a map from offset in the file to the function node
            # For tree-sitter nodes the offset can be computed as `function_node.start_byte`` and for Clang nodes the 
            # offset can be computed as `extent.start.offset` 
            clang_functions = get_all_functions_clang(file_path)
            offset_to_clang_node_map = {clang_fn_node.extent.start.offset: clang_fn_node for clang_fn_node in clang_functions}

            # Analyze each function in the file
            for ts_fn_node in ts_fn_nodes:
                assert ts_fn_node.type == 'function_definition'
                                
                if ts_fn_node.start_byte not in offset_to_clang_node_map:
                    # In many cases clang would filter functions that are under "#ifdef" directive where the 
                    # corresponding macro is not defined
                    continue
                
                clang_fn_node = offset_to_clang_node_map[ts_fn_node.start_byte]

               # Extract the docstring using tree-sitter 
                docstring = BDEMiner._get_fn_docstring(ts_fn_node, clang_fn_node)

                fn_data = BDEMiner.create_function_data(file_path, ts_fn_node, clang_fn_node, docstring=docstring)
                
                fns.append(fn_data)

                if len(docstring) > 0:
                    count_functions_with_docstrings += 1

                if len(docstring) > 0:
                    if len(tests) > 0: # Count functions that have unit tests
                        count_functions_with_tests += 1

        print('Total files:', count_cpp_files)
        print('Total files with test files:', count_cpp_files_with_tests)
        print('Total functions:', len(fns))
        print('Functions with docstrings:', count_functions_with_docstrings)
        print('Functions with tests and docstrings:', count_functions_with_tests)

        Path("data").mkdir(parents=True, exist_ok=True)

        return fns
    
    @staticmethod
    def _get_fn_docstring(ts_fn_node, clang_fn_node) -> str:
        d1 = get_ts_fn_node_docstring(ts_fn_node)
        d2 = get_docstring_from_headers(clang_fn_node)
        docstring = ''
        if len(d1) > 0:
            docstring = d1
        elif len(d2) > 0:
            docstring = d2
        return docstring

    @staticmethod
    def _get_call_graph(function_nodes, function_node_to_name, named_functions):
        """
        Create a local call graph within the given file
        """
        call_graph = defaultdict(list) # A list of edges in the call graph for each file
        for function1_name in named_functions:
            for function2_node in function_nodes:
                function2_name = function_node_to_name[function2_node]
                if function1_name == function2_name or function2_name == None:
                    continue
                if function1_name in function2_node.text.decode("utf-8"):
                        # Add a call edge from function2 to function1
                    call_graph[function2_name].append(function1_name)
        return call_graph

    @staticmethod
    def _get_calls_relations(function_nodes, function_node_to_name, call_graph):
        """
        # Do a DFS to compute all functions called transitively by function_node
        """
        transitive_calls_relation = defaultdict(list) 
        def dfs(source_function_name, called):
            called[source_function_name] = True
            for next_function_name in call_graph[source_function_name]:
                if not called[next_function_name]:
                    dfs(next_function_name, called)

        for function_node in function_nodes:
            called = defaultdict(bool)
            function_name = function_node_to_name[function_node]
            dfs(function_name, called)
            transitive_calls_relation[function_name] = [fname for fname in called if called[fname] == True]
        return transitive_calls_relation

    @staticmethod
    def _get_test_map(count_cpp_files_with_tests, named_functions, transitive_calls_relation, test_file):
        """
        Returns a map from function to list of test functions that it calls
        """
        tests = defaultdict(set)  
        if test_file.is_file():
            count_cpp_files_with_tests += 1
            test_function_nodes = get_all_ts_function_nodes(str(test_file))

            # compute test-function relations
            for test_function_node in test_function_nodes:
                test_function_name = get_function_name(test_function_node)
                for function_name in named_functions:
                    if function_name in test_function_node.text.decode("utf-8"): 
                        # If the functon name is present in the body of the test
                        for transitively_called_function in transitive_calls_relation[function_name]:
                            tests[transitively_called_function].add(test_function_name)
        return tests


class BMQMiner(CodeMiner):
    """
    This implementation of miner makes specific assumptions that hold for Bloomberg's BlazingMQ repository 
    https://github.com/bloomberg/blazingmq
    """
    def __init__(self, source, use_cache=True):
        super().__init__(source, use_cache)

    @staticmethod
    def _analyze_source(path) -> Iterator[FunctionData]:
        """
        Recursively analyze all cpp files in directory at this path and its subdirectories 
        """
        path = path + "/src/groups/bmq"
        cpp_files = list(Path(path).rglob("*.cpp"))
        count_cpp_files = 0
        count_functions_with_docstrings = 0
        fns: Iterator[FunctionData] = []
        pbar = tqdm(total=len(cpp_files))

        for file_path in cpp_files:
            pbar.update(1)
            if str(file_path).endswith('.t.cpp') or 'build' in str(file_path):
                # TODO: 'build' in file_path is hacky. Fix this
                continue
            
            count_cpp_files += 1
            # Check if the corresponding test file exists
            test_file = Path(str(file_path).replace('cpp', 't.cpp'))
            if not test_file.is_file():
                continue

            # ts_fn_nodes is a list of tree-sitter function nodes in the given file
            ts_fn_nodes: Iterator[Node] = get_all_ts_function_nodes(str(file_path)) 

            # Get the map of clang nodes for each functions as a map from offset in the file to the function node
            # For tree-sitter nodes the offset can be computed as `function_node.start_byte`` and for Clang nodes the 
            # offset can be computed as `extent.start.offset` 
            clang_functions = get_all_functions_clang(file_path)
            offset_to_clang_node_map = {clang_fn_node.extent.start.offset: clang_fn_node for clang_fn_node in clang_functions}

            # Analyze each function in the file
            for ts_fn_node in ts_fn_nodes:
                assert ts_fn_node.type == 'function_definition'
                                
                if ts_fn_node.start_byte not in offset_to_clang_node_map:
                    # In many cases clang would filter functions that are under "#ifdef" directive where the 
                    # corresponding macro is not defined
                    continue
                
                clang_fn_node = offset_to_clang_node_map[ts_fn_node.start_byte]

               # Extract the docstring using tree-sitter 
                docstring = BMQMiner._get_fn_docstring(ts_fn_node, clang_fn_node)

                fn_data = BMQMiner.create_function_data(file_path, ts_fn_node, clang_fn_node, docstring=docstring)
                
                fns.append(fn_data)

                if len(docstring) > 0:
                    count_functions_with_docstrings += 1

        print('Total files:', len(cpp_files))
        # print('Total functions:', len(fns))
        print('Total functions with tests:', len(fns))
        print('Functions with tests+docstrings:', count_functions_with_docstrings)

        Path("data").mkdir(parents=True, exist_ok=True)
        return fns
    
    @staticmethod
    def _get_fn_docstring(ts_fn_node, clang_fn_node) -> str:
        d1 = get_ts_fn_node_docstring(ts_fn_node)
        d2 = get_docstring_from_headers(clang_fn_node)
        docstring = ''
        if len(d1) > 0:
            docstring = d1
        elif len(d2) > 0:
            docstring = d2
        return docstring