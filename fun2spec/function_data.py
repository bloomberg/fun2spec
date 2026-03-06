# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from typing import Iterable
from tree_sitter import Node
from clang.cindex import TypeKind 

class ReturnType:
    name: str
    category: TypeKind
    def __init__(self, name: str, category: TypeKind) -> None:
        self.name = name
        self.category = category
    
    def __str__(self) -> str:
        return f"ReurnType({self.name}, {self.category})"

class FunctionData:
    """
    The class represents data corresponding to a single function in the code to be analyzed.

    Attributes
    ----------
    offset: It is the byte offset in the file. This is used as an unique key to identify functions in addition to the file path. 
    """
    function_name: str
    return_type: ReturnType
    file_path: str
    function_string: str
    tests: Iterable[Node]
    docstring: str
    offset: int
    idx: int
    args: Iterable[str]
    test_string: str  # This is useful for HumanEval with a file having function+tests 

    def __init__(
            self, 
            function_name, 
            file_path, 
            function_string, 
            offset, 
            return_type=None, 
            idx=-1, 
            docstring="", 
            tests=[], 
            args=[],
            test_string=None,
            ground_truth=None
            ) -> None:
        self.function_name = function_name
        self.file_path = file_path
        self.function_string = function_string
        self.offset = offset
        self.docstring = docstring.replace('\n','')
        self.tests = tests
        self.return_type = return_type
        self.idx = idx
        self.args = args
        self.test_string = test_string
        self.ground_truth = ground_truth

    def __str__(self) -> str:
        return 'Function Name: ' + str(self.function_name) + '\n'\
            + 'File Path: ' + str(self.file_path) + '\n'\
            + 'Offset: ' + str(self.offset) + '\n'\
            + 'Function:\n' + self.function_string + '\n' 
    