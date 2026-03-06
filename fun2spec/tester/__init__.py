# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
Given a function, corresponding unit-test and proposed contract. Check if the assertion holds for tests.
"""
from common import SourceType
from tester.bmq_tester import BMQTester
from tester.contract_tester import FileTester
from tester.humaneval_tester import HumanEvalTester
from tester.bde_tester import BDETester
from tester.fsc_tester import FormalSpecCPPTester

def get_contract_tester(source_type: SourceType, root_dir, **kwargs):
    """
    Map each source type to its corresponding tester. 
    """
    if source_type == SourceType.BDE:
        return BDETester(root_dir, **kwargs)
    elif source_type == SourceType.BMQ:
        return BMQTester(root_dir, **kwargs)
    elif source_type == SourceType.humaneval:
        return HumanEvalTester(root_dir, **kwargs)
    elif source_type == SourceType.FSC:
        return FormalSpecCPPTester(root_dir, **kwargs)
    elif source_type == SourceType.file:
        return FileTester(root_dir)
    