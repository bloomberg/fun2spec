# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
This file contains code for Tree-sitter based parsing.
"""
import tree_sitter_cpp as tscpp
from typing import Iterable, Iterator, Optional
from tree_sitter import Node
from pathlib import Path
from tree_sitter import Language, Parser

ts_parser = Parser(Language(tscpp.language()))
                
def get_all_ts_function_nodes(file_path: str) -> Iterable[Node]:
    file_path = file_path.lstrip(' ')
    file = Path(file_path)
    file_content = file.read_text()
    tree = ts_parser.parse(bytes(file_content, "utf8"))
    return search_functions_in_nodes(tree.root_node)
    
def search_functions_in_nodes(root_node) -> Iterable[Node]:
    ts_fn_nodes = []
    for node in root_node.children:
        if node.type == 'function_definition':
            ts_fn_nodes.append(node)
        if len(node.children) > 0:
            ts_fn_nodes += search_functions_in_nodes(node)
    return ts_fn_nodes


def find_child_node_by_path(node: Node, grammar_name_path: Iterable[str]) -> Optional[Node]:
    if len(grammar_name_path) == 0:
        return node
    cur_node = node
    for child_node in cur_node.children:
        if child_node.grammar_name == grammar_name_path[0]:
            return find_child_node_by_path(child_node, grammar_name_path[1:])
    return None

def get_function_name(ts_fn_node: Node) -> str:
    """
    TODO: This way o extracting name of the function is not reliable. It is easier to extract the name through Clang-based parsing.
    Thus remove this function in future when all of its usages are removed. 
    """
    fname = find_child_node_by_path(ts_fn_node, ['function_declarator', 'identifier'])
    if fname: return fname.text.decode("utf-8")
    
    fname = find_child_node_by_path(ts_fn_node, ['function_declarator', 'qualified_identifier']) 
    if fname: return fname.children[2].text.decode("utf-8")

    fname = find_child_node_by_path(ts_fn_node, ['function_declarator', 'template_function', 'identifier']) 
    if fname: return fname.text.decode("utf-8")

    # Some cases with functions related to operator overloading, class destructors may reach this point
    return None

def get_ts_fn_node_docstring(ts_fn_node: Node) -> str:
    assert ts_fn_node.type == "function_definition", ts_fn_node.type
    doc_string = ""
    for node in ts_fn_node.children:
        if node.type == 'comment':
            doc_string += node.text.decode("utf-8").replace('//', '')
    return doc_string.replace('\n','')


def validate_expression(assertion: str, symbols: Iterator[str]) -> bool:
    """
    Check if the assertion is a valid expression that uses inputs only from provided symbols. 
    At this point this function ignores all the function and method calls, and conservatively assumes they are
    valid. 
    """
    # Store the assertion in a temp file and get the parsed tree from C++
    ts_tree = ts_parser.parse(bytes(f"{assertion};", "utf8"))
    is_valid = True
    queue = [ts_tree.root_node]

    while len(queue) > 0:
        node = queue.pop()
        # print(node.text.decode("utf-8"), node.type)
        if node.type == 'identifier':
            id_name = node.text.decode("utf-8")
            is_valid = is_valid and (id_name in symbols)
        elif node.type == 'call_expression':
            if node.children[0].type == 'field_expression':
                # check if it is a method call then the callee should be in-context
                queue.append(node.children[0].children[0])

            for c in node.children[1].children: # Go through the args and skip the function name for now
                queue.append(c)
        else:
            for c in node.children: # push all children
                queue.append(c)
    
    return is_valid
