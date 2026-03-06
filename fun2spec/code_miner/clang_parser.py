# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import re
import common
from clang.cindex import CursorKind, Index, Cursor, TranslationUnit

def search_functions_in_nodes_clang(node: Cursor) -> list[Cursor]:
    all_functions = []
    def search(node):
        if node.kind == CursorKind.FUNCTION_DECL or node.kind == CursorKind.CXX_METHOD:
            all_functions.append(node)

        for c in node.get_children():
            search(c) 
    search(node)
    return all_functions

def get_all_functions_clang(file_path: str) -> list[Cursor]:
    index = Index.create()

    if common.source_type != common.SourceType.BDE:
        args = common.CLANG_HEADERS.split()
    else:
        args = None

    tu = index.parse(
        file_path,
        args=args, 
        options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD | TranslationUnit.PARSE_INCLUDE_BRIEF_COMMENTS_IN_CODE_COMPLETION
        )
    
    clang_functions = search_functions_in_nodes_clang(tu.cursor)

    # This gives too many warnings for BDE so commenting it for now
    # TODO: check if it is necessary to address these warnings
    # for diag in tu.diagnostics:
    #     if diag.severity == diag.Fatal:
    #         for clang_funcion in clang_functions:
    #             clang_funcion.parsing_error = f"Warning: clang parsing encountered errors!\n{diag.location}\n{diag.spelling}\n{diag.option}"

    return clang_functions


def get_docstring_from_headers(clang_fn_node: Cursor) -> str:
    """
    NOTE: This assumes that the comments on the header files are written in a specific format (This is True for BDE and BMQ).
    
    Case 1:
    Where the comment is right above function definition each line starting with "//" or "///".

    Case 2: 
    In the header file, where comments are followed by the function signature. 
    ```
    function_name(...)
    // ... 
    // ...
    ```

    If this assumption does not hold for any repository, this function needs to be updated. 
    """
    # Extract comments from function def
    prev_lines = common.get_file_lines(str(clang_fn_node.extent.start.file))[:clang_fn_node.extent.start.line-1]
    cur_idx = len(prev_lines)-1
    doc = ''
    while cur_idx >= 0:
        cur_line = prev_lines[cur_idx]
        cur_line = re.sub(r"[\n\t]*", "", cur_line)
        cur_line = re.sub(r"[\s]+", " ", cur_line) # Replace multiple spaces with one

        if cur_line.startswith('//'):
            cur_line = cur_line.replace('/', '')
            doc = cur_line + doc
        else:
            break
        cur_idx -= 1

    if len(doc) > 0:
        return doc

    # Extract comment from the header
    header_fn = clang_fn_node.canonical
    if header_fn.extent.start.file.name.endswith('.h'):
        try:
            header_fn_lines = common.get_file_lines(str(header_fn.extent.start.file))[header_fn.extent.end.line:]
            m1 = re.match(r"([ \t]*\/\/.*[\t \n])*", ''.join(header_fn_lines))
            m = re.findall(r"\/\/.*[\t \n]", m1.group(0))
            doc = ''.join(m).replace('//', '')
            return doc.replace('\n','')
        except:
            pass
    
    return ''
