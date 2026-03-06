# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from common import SourceType, get_source_name
from code_miner.code_miner import BDEMiner, BMQMiner, FileMiner, HumanEvalMiner, CodeMiner, FormalSpecCPPMiner

def get_code_miner(source: str, use_cache=True) -> CodeMiner:
    source_type = get_source_name(source)
    if source_type == SourceType.BDE:
        return BDEMiner(source=source, use_cache=use_cache)
    elif source_type == SourceType.BMQ:
        return BMQMiner(source=source, use_cache=use_cache)
    elif source_type == SourceType.humaneval:
        return HumanEvalMiner(source=source, use_cache=use_cache)
    elif source_type == SourceType.FSC:
        return FormalSpecCPPMiner(source=source, use_cache=use_cache)
    elif source_type == SourceType.file:
        return FileMiner(source=source)
