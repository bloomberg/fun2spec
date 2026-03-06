# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Test utility functions that are created on top of the tree-sitter library.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + '/../fun2spec/')
import code_miner.ts_parser as ts_parser
from tree_sitter import Node
from tree_sitter import Language, Parser
import tree_sitter_cpp as tscpp
import unittest
from clang.cindex import CursorKind, Index, Cursor

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

class TestParsing(unittest.TestCase):
    def get_function_node(self, function_str: str) -> Node:
        tree = parser.parse(bytes(function_str, "utf8"))
        return ts_parser.search_functions_in_nodes(tree.root_node)[0]

    def get_clang_function_node(self, function_str: str) -> Cursor:
        tmp_filename = '/tmp/t.txt'
        with open(tmp_filename, 'w') as f:
            f.write(function_str)
        index = Index.create()
        tu = index.parse(tmp_filename)
        return tu.cursor

    # Test validate expression
    def test_validate_expr1(self):
        assert ts_parser.validate_expression('a+b+c', ['a', 'b', 'c'])

        # Should fail because 'c' does not exist in the expression
        assert not ts_parser.validate_expression('a+b+d', ['a', 'b', 'c'])

        assert ts_parser.validate_expression('a+b+3', ['a', 'b', 'c'])

        assert ts_parser.validate_expression('((f1 >= f2) + size(f3))', ['f1', 'f2', 'f3'])

        assert not ts_parser.validate_expression('((f1 >= f2) + size(f3))', ['f1', 'f2'])

        assert not ts_parser.validate_expression('((f1 >= f2) + f3.size())', ['f1', 'f2'])


if __name__ == '__main__':
    unittest.main()
