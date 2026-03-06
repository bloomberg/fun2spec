# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Test LLM related functionality.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.realpath(__file__)) + '/../fun2spec/')
import unittest
from llm.prompt_builder import build_prompt
from function_data import FunctionData

class TestLLM(unittest.TestCase):
    def test_prompt_builder(self):
        mock_fn_data = FunctionData('hello_world', None, "void hello_world()\{\}", 12, return_type=None, docstring="Print hellow world")
        prompt = build_prompt(mock_fn_data)
        # print(prompt)
        # assert prompt.endswith('POST(res_tmp :')
    
    def test_prompt_builder_with_doc(self):
        mock_fn_data = FunctionData('hello_world', None, "void hello_world()\{\}", 12, return_type=None, docstring="Print hellow world")
        prompt = build_prompt(mock_fn_data, add_doc=False)
        # print(prompt)
        # assert prompt.endswith('POST(res_tmp :')
        assert not 'Documentation:' in prompt

    def test_prompt_builder_without_doc(self):
        mock_fn_data = FunctionData('hello_world', None, "void hello_world()\{\}", 12, return_type=None, docstring="Print hellow world")
        prompt = build_prompt(mock_fn_data, add_doc=True)
        print(prompt)
        # assert prompt.endswith('POST(res_tmp :')
        assert 'Documentation:' in prompt

if __name__ == '__main__':
    unittest.main()
