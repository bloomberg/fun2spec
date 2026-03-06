# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Test utility functions that are created on top of the clang library.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + '/../fun2spec/')
import unittest
from clang.cindex import CursorKind, Index, Cursor, TypeKind
from clang_parser import find_function

class TestParsing(unittest.TestCase):
    def get_clang_function_node(self, function_str: str) -> Cursor:
        tmp_filename = '/tmp/t.cpp'
        with open(tmp_filename, 'w') as f:
            f.write(function_str)
        index = Index.create()
        tu = index.parse(tmp_filename)
        return find_function(tu.cursor)[0]

    def test_void(self):
        function_str = f"""void print(int k){{}}"""
        fn_node = self.get_clang_function_node(function_str)
        assert fn_node.result_type.kind == TypeKind.VOID
    
    def test_int(self):
        function_str = f"""int count(Severity::Level value){{return 0;}}"""
        fn_node = self.get_clang_function_node(function_str)
        assert fn_node.result_type.kind == TypeKind.INT

    def test_static_inline(self):
        function_str = f"""static inline void mix1(unsigned int& a, unsigned int& b, unsigned int& c){{}}"""
        fn_node = self.get_clang_function_node(function_str)
        assert fn_node.result_type.kind == TypeKind.VOID

    # def test_constructor(self):
    #     function_str = f"""inline BitPtrDiff(size_t value): d_hi(value >> k_NUM_LO_BITS), d_lo(value & k_USED_LO_MASK){{}}"""
    #     fn_node = self.get_clang_function_node(function_str)
    #     print(fn_node.result_type.kind )
    #     assert fn_node.result_type.kind == TypeKind.VOID

    def test_destructor(self):
        function_str = f"""class ThrowsWithinDestructor{{ void add() {{}} }}"""
        fn_node = self.get_clang_function_node(function_str)
        assert fn_node.result_type.kind == TypeKind.VOID
    
    # def test_object(self):
    #     function_str = f"""LinkNamespace::Link get_link() {{}}"""
    #     fn_node = self.get_clang_function_node(function_str)
    #     print(get_function_return_type(fn_node))
    #     assert get_function_return_type(fn_node).category == TypeCategory.object

if __name__ == '__main__':
    unittest.main()