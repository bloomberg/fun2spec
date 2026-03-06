# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from enum import StrEnum
import hashlib
from pathlib import Path
import subprocess
import re
from typing import Iterator, Optional
import os
import sys
import glob

# Portable libclang configuration
# Users can override these with environment variables
def _find_libclang():
    """Attempt to find libclang library on the system."""
    # Check environment variable first
    if 'LIBCLANG_PATH' in os.environ:
        return os.environ['LIBCLANG_PATH']

    # Common paths across different systems
    search_paths = []

    if sys.platform.startswith('linux'):
        # Linux paths
        search_paths.extend([
            '/usr/lib/llvm-*/lib/libclang.so*',
            '/usr/lib/x86_64-linux-gnu/libclang*.so*',
            '/usr/lib/libclang*.so*',
        ])
    elif sys.platform == 'darwin':
        # macOS paths
        search_paths.extend([
            '/usr/local/opt/llvm/lib/libclang.dylib',
            '/Library/Developer/CommandLineTools/usr/lib/libclang.dylib',
            '/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libclang.dylib',
        ])
    elif sys.platform == 'win32':
        # Windows paths
        search_paths.extend([
            'C:/Program Files/LLVM/bin/libclang.dll',
            'C:/Program Files (x86)/LLVM/bin/libclang.dll',
        ])

    # Try to find the library
    for pattern in search_paths:
        matches = glob.glob(pattern)
        if matches:
            # Return the first match (or latest version for versioned libs)
            return sorted(matches)[-1]

    # Fallback to default Linux path if nothing found
    return '/usr/lib/llvm-14/lib/libclang.so.1'

def _get_clang_headers():
    """Get clang headers configuration."""
    # Check environment variable first
    if 'CLANG_HEADERS' in os.environ:
        return os.environ['CLANG_HEADERS']

    # Default headers (works on most Linux systems)
    return '-std=c++14 -stdlib=libstdc++ -I/usr/include/x86_64-linux-gnu/c++/11 -I/usr/include/c++/11'

LIBCLANG_PATH = _find_libclang()
CLANG_HEADERS = _get_clang_headers()

######### Related to Source of the code ############# 

class SourceType(StrEnum):
    BDE = 'bde'                 # https://github.com/bloomberg/bde
    BMQ = 'bmq'                 # https://github.com/bloomberg/blazingmq
    humaneval = 'humaneval'     # C++ version of humaneval from https://huggingface.co/datasets/THUDM/humaneval-x
    FSC = "fsc"                 # https://github.com/MadhuNimmo/FormalSpecCpp
    file = 'file'               # For single file

    def __str__(self) -> str:
        return self.value
    
source_type: SourceType = None # Global variable to maintain the source type during analysis

def get_source_name(source: str) -> SourceType:
    # Keeping it simple for now
    if 'bde' in source:
        return SourceType.BDE
    elif 'bmq' in source or 'blazingmq' in source:
        return SourceType.BMQ
    elif 'humaneval' in source or 'human-eval' in source or 'HumanEval' in source:
        return SourceType.humaneval
    elif 'fsc' in source.lower() or 'formalspeccpp' in source.lower():
        return SourceType.FSC
    elif source.endswith('.cpp'):
        return SourceType.file
    else:
        raise ValueError('Unrecognized repository path. Currently support BDE or human-eval.')

######### Related to the Generator ############# 

class GeneratorType():
    Fun2Spec = 'fun2spec' # default to the current tool
    Daikon = 'daikon'    # A basline tool https://plse.cs.washington.edu/daikon

def get_generator(gen_name: str) -> GeneratorType:
    if gen_name == 'daikon':
        return GeneratorType.Daikon
    return GeneratorType.Fun2Spec

########## Other stuff  ############# 

def get_project_path() -> str:
    # Assuming common.py is present in fun2spec/fun2spec/common.py
    return str(Path(__file__).parent.parent.resolve())

# Utility function, move it later
def get_file_lines(file_path: str) -> Iterator[str]:
    file_lines = []
    with open(file_path, 'r') as f:
        for line in f.readlines():
            file_lines.append(line)
    return file_lines

def ignore_patterns(patterns):
    def _ignore_patterns(path, names):
        for pattern in patterns:
            if pattern in path:
                return True
        return False
    return _ignore_patterns

def persistent_hash(s: str) -> int:
    return int(hashlib.sha256(str(s).encode('utf-8')).hexdigest(), 16)

def run_bash(command:str, timeout=50) -> Optional[subprocess.Popen]:
    print('Executing bash command:', command)
    try:
        output = subprocess.run(command, shell=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print('Subprocess for command timed out!')
        output = None
    return output

def extract_reasoning(cd: str) -> Optional[str]:
    try:
        reasoning: str = re.search(r'Reasoning:((.|\n)*)Post', cd).group(1)
        reasoning = reasoning.lstrip('\n')
    except:
        reasoning = None
    return reasoning

def extract_predicate(cd) -> Optional[str]: 
    try:
        m = re.search(r'POST\((.*)\)', cd)
        predicate = m.group(1)
        if "POST" in predicate:
            predicate = predicate.split("POST")[0].rstrip()[:-1]
    except:
        predicate = None
    return predicate

# Run the tests
if __name__ == "__main__":
    # Test 1
    input = "Reasoning:\nLet's think about this step by step. The function checks various conditions and returns -1 in several scenarios indicating an error. The return value is 0 only if all checks pass successfully. Therefore, the function either returns -1 for errors or 0 for success.\nPostcondition:\nPOST(res_tmp == 0 || res_tmp == -1) POST(res_tmp == 0 || res_tmp == -1)"
    predicate  = extract_predicate(input)
    assert predicate == "res_tmp == 0 || res_tmp == -1"

import logging

# This is the setup for Python logging
def setup_logging(level=None):
    """
    Configure the root logger for both application and test usage.
    
    This function is safe to call multiple times - it will only configure
    logging once to avoid duplicate handlers.
    
    Args:
        level: Override the logging level. If None, uses the LOG_LEVEL 
               environment variable or defaults to INFO.
    
    Returns:
        The root logger
    """ 
    # Determine the logging level
    if level is None:
        # Get level from environment or default to INFO
        level_name = os.environ.get('LOG_LEVEL', 'INFO')
        level = getattr(logging, level_name.upper(), logging.INFO)
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Clear any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set the logging level
    root_logger.setLevel(level)
    
    # Create a stdout handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('[%(asctime)s-%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
        
    return root_logger