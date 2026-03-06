# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from lark import Lark, Token, Tree
import logging
logger = logging.getLogger(__name__)

grammar = """
    start: expression -> start_expr

    // Logical expressions
    expression: implication
              | quantifier_expression
              | comp_expression
              | "(" expression ")"

    implication : expression "==>" expression -> implication
    !comp_expression: operation_expression 
                    | expression ( "||" | "&&" ) expression -> binary_op

    !quantifier_expression: exists_expr | forall_expr
    exists_expr: EXISTST "(" expression "," expression "," CNAME "," expression ")" -> exists_expr
    forall_expr: FORALL "(" expression "," expression "," CNAME "," expression ")" -> forall_expr
    EXISTST.2: "EXISTS"
    FORALL.2: "FORALL"

    operation_expression: binary_op | unary_expr 
    unary_expr: unary | atom

    !binary_op : expression binary_operator expression -> binary_op
    !unary: UNARY_OP expression -> unary_op
    !binary_operator: COMPARISON_OP | ARITHMETIC_OP | BITWISE_OP

    // Atoms: Base cases like variables, literals, functions, etc.
    atom: variable
        | literal
        | string_literal
        | pointer_access
        | array_access
        | function_call 
        | "(" expression ")"  -> paren_expr
        | atom "." atom -> dot_expr
        | atom "->" atom -> arrow_expr
        | atom "::" atom -> scope_res

    // Components
    variable: CNAME
    literal: NUMBER | SIGNED_NUMBER | HEX_NUMBER | OCT_NUMBER | BIN_NUMBER
    !string_literal: /'.'/ | /".*?"/
    pointer_access: "*" expression
    array_access: expression "[" expression "]" -> array_access
    function_call: expression "(" (expression ("," expression)*)? ")"  -> function_call

    // Operators
    COMPARISON_OP: "==" | "!=" | "<" | ">" | "<=" | ">="
    ARITHMETIC_OP: "+" | "-" | "*" | "/" | "%" | "**"
    BITWISE_OP: "&" | "|" | "^" | "<<" | ">>"
    UNARY_OP: "!" | "-" | "~" | "++" | "--" | "*" | /(?<!&)&(?!&)/

    HEX_NUMBER.2: /0x[\da-f]*(u)?/i
    OCT_NUMBER.2: /0o[0-7]*(u)?/i
    BIN_NUMBER.2 : /0b[0-1]*(u)?/i

    %import common.CNAME
    %import common.NUMBER
    %import common.SIGNED_NUMBER
    %import common.ESCAPED_STRING
    %import common.WS
    %ignore WS
"""

# Define the transformer to handle implication transformation
class Transformer:
    def transform(self, tree):
        """Recursively transform the parse tree into a C++ expression string."""
        if isinstance(tree, Tree):
            # Process each type of expression according to grammar rules
            if tree.data == "start_expr":
                return self.transform(tree.children[0])
            elif tree.data == "paren_expr":
                # Parentheses around the inner expression
                return f"({self.transform(tree.children[0])})"
            elif tree.data == "function_call":
                # Parentheses around the inner expression
                arg_str = ''
                for i in range(1, len(tree.children)):
                    if i > 1:
                        arg_str += ","
                    arg_str += self.transform(tree.children[i])
                return f"{self.transform(tree.children[0])}({arg_str})"
            elif tree.data == "exists_expr":
                # Convert EXISTS(start, end, var, condition) to lambda
                start = self.transform(tree.children[1])
                end = self.transform(tree.children[2])
                var_name = tree.children[3].value  # CNAME token
                condition = self.transform(tree.children[4])
                
                return f"([&]() {{ for(int {var_name} = {start}; {var_name} < {end}; {var_name}++) {{ if({condition}) return true; }} return false; }})()"
                
            elif tree.data == "forall_expr":
                # Convert FORALL(start, end, var, condition) to lambda
                start = self.transform(tree.children[1])
                end = self.transform(tree.children[2])
                var_name = tree.children[3].value  # CNAME token
                condition = self.transform(tree.children[4])
                
                return f"([&]() {{ for(int {var_name} = {start}; {var_name} < {end}; {var_name}++) {{ if(!({condition})) return false; }} return true; }})()"
            elif tree.data == "implication":
                # Replace A ==> B with !A || B
                left = self.transform(tree.children[0])
                right = self.transform(tree.children[1])
                return f"!({left}) || {right}"
            elif tree.data == "binary_op":
                # binary operation
                left = self.transform(tree.children[0])
                right = self.transform(tree.children[2])
                return f"{left} {self.transform(tree.children[1])} {right}"
            elif tree.data == "dot_expr":
                left = self.transform(tree.children[0])
                right = self.transform(tree.children[1])
                return f"{left}.{right}"
            elif tree.data == "scope_res":
                left = self.transform(tree.children[0])
                right = self.transform(tree.children[1])
                return f"{left}::{right}"
            elif tree.data == "arrow_expr":
                left = self.transform(tree.children[0])
                right = self.transform(tree.children[1])
                return f"{left} -> {right}"
            elif tree.data == "unary_op":
                # unary operation
                return f"{self.transform(tree.children[0])}{self.transform(tree.children[1])}"
            elif tree.data == "array_access":
                return  f"{self.transform(tree.children[0])}[{self.transform(tree.children[1])}]"
            else:
                return f"{self.transform(tree.children[0])}"
        elif isinstance(tree, Token):
            # Directly return the token's value for characters
            return tree.value
        return ""

# Parse and transform function
def convert_postcondition_to_cpp(postcondition):
    # Initialize the parser with the grammar
    parser = Lark(grammar, start='start', parser='earley')

    try:
        parse_tree = parser.parse(postcondition)
            
        # Initialize custom transformer and transform the parse tree
        transformer = Transformer()
        transformed_expr = transformer.transform(parse_tree)
    
    except Exception as e:
        logger.info(f"Warning: transformation of cpp {postcondition} postcondition failed!\nError\n{e}")
        return None

    # Re-wrap in POST
    return f"{transformed_expr}"


def match_postcondition(p1: str, p2: str) -> bool:
    p1_clean = p1.strip().replace(" ", "").replace("\n", "")
    p2_clean = p2.strip().replace(" ", "").replace("\n", "")
    return p1_clean == p2_clean

def test_convert_postcondition_to_cpp():
    # Test case 1: Simple implication
    postcondition = "(a == 1 ==> b == 2)"
    expected = "(!(a == 1) || b == 2)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 2: Implication with AND
    postcondition = "(x > 0 ==> y < 10) && (z == 5)"
    expected = "(!(x > 0) || y < 10) && (z == 5)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 3: Implication with OR
    postcondition = "(x != y ==> a == b) || (c != d)"
    expected = "(!(x != y) || a == b) || (c != d)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 4: Nested implications
    postcondition = "((a == 0 ==> b > 1) && (c == d)) ==> e != f"
    expected = "!(((!(a == 0) || b > 1) && (c == d))) || e != f"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 5: Function call within implication
    postcondition = "(myFunc(x) > 0 ==> result != -1)"
    expected = "(!(myFunc(x) > 0) || result != -1)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 6: Multiple implications with AND and OR
    postcondition = "(a == b ==> c != d) && (x > y ==> myFunc(z) == 0)"
    expected = "(!(a == b) || c != d) && (!(x > y) || myFunc(z) == 0)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

     # Test case 7: Array element within implication
    postcondition = "(arr[0] == 10 ==> arr[1] != 5)"
    expected = "(!(arr[0] == 10) || arr[1] != 5)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 8: String comparison within implication
    postcondition = '(str1 == "hello" ==> str2 != "world")'
    expected = '(!(str1 == "hello") || str2 != "world")'
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 9: Pointer dereference within implication
    postcondition = "(*(ptr) == 3 ==> *ptr2 != 4)"
    expected = "(!(*(ptr) == 3) || *ptr2 != 4)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 10: Reference variable in implication
    postcondition = "(refVar == 20 ==> refVar2 != 30)"
    expected = "(!(refVar == 20) || refVar2 != 30)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 11: Method call with multiple arguments in implication
    postcondition = "(abc.isEqual(a, b) ==> compute(c, d, e) > 0)"
    expected = "(!(abc.isEqual(a, b)) || compute(c, d, e) > 0)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 12: Nested expressions with arrays and pointers
    postcondition = "(arr[0] == *(ptr + 1) ==> arr[2] != refVar)"
    expected = "(!(arr[0] == *(ptr + 1)) || arr[2] != refVar)"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 13: Multiple conditions with strings and arrays
    postcondition = '(str1 == "test" ==> arr[0] == 5) && (arr[1] != 3 ==> str2 == "pass")'
    expected = '(!(str1 == "test") || arr[0] == 5) && (!(arr[1] != 3) || str2 == "pass")'
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 14: Condition including '\\' and '/'
    postcondition = "(ch == '/' || ch == '\\')"
    expected = "(ch == '/' || ch == '\\')"
    transformed = convert_postcondition_to_cpp(postcondition)
    assert match_postcondition(transformed, expected)

    # Test case 15: Something from the actual BDE test case
    postcondition = "(namespaceUri.empty() ==> res_tmp == -1) && (!namespaceUri.empty() ==> res_tmp != -1)"
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = "(!(namespaceUri.empty()) || res_tmp == -1) && (!(!namespaceUri.empty()) || res_tmp != -1)"
    assert match_postcondition(transformed, expected)

    # Test case 16: Something from the actual BDE test case
    postcondition = "(val >= 0x110000U ==> res_tmp == 0)"
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = "(!(val>=0x110000U) || res_tmp==0)"
    assert match_postcondition(transformed, expected)

    # Test case 17: Something from the actual BDE test case
    postcondition = "(error >= ErrorInfo::e_ERROR ==> res_tmp == -1)"
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = "(!(error>=ErrorInfo::e_ERROR) || res_tmp==-1)"
    assert match_postcondition(transformed, expected)    

    # Test case 18: Something from the actual BDE test case
    postcondition = "&res_tmp == &stream && (bdlb::Float::classifyFine(object) >= bdlb::Float::k_POSITIVE_INFINITY && bdlb::Float::classifyFine(object) <= bdlb::Float::k_SNAN ==> res_tmp.fail())"
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = "&res_tmp == &stream && (!(bdlb::Float::classifyFine(object) >= bdlb::Float::k_POSITIVE_INFINITY && bdlb::Float::classifyFine(object) <= bdlb::Float::k_SNAN) || res_tmp.fail())"
    assert match_postcondition(transformed, expected)

    # Test case 19: Something from the actual BDE test case
    postcondition = "((nameFilter != nullptr) ==> (res_tmp == filteredNameBuffer->c_str())) && ((nameFilter == nullptr) ==> (res_tmp == originalName))"
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = "(!((nameFilter != nullptr)) || (res_tmp == filteredNameBuffer -> c_str())) && (!((nameFilter == nullptr)) || (res_tmp == originalName))"
    assert match_postcondition(transformed, expected)

    # Test case 20: Test quantifiers to lambda
    postcondition = """((res_tmp == true) ==> EXISTS(0, numbers.size()-1, i, EXISTS(i+1, numbers.size(), j, abs(numbers[i] - numbers[j]) < threshold)))
     && 
     ((res_tmp == false) ==> FORALL(0, numbers.size()-1, i, FORALL(i+1, numbers.size(), j, abs(numbers[i] - numbers[j]) >= threshold)))"""
    transformed = convert_postcondition_to_cpp(postcondition)
    expected = """
    (!((res_tmp == true)) 
            || ([&]() { for(int i = 0; i < numbers.size() - 1; i++) { if(([&]() { for(int j = i + 1; j < numbers.size(); j++) { if(abs(numbers[i] - numbers[j]) < threshold) return true; } return false; })()) return true; } return false; })()) 
    && (!((res_tmp == false)) 
            || ([&]() { for(int i = 0; i < numbers.size() - 1; i++) { if(!(([&]() { for(int j = i + 1; j < numbers.size(); j++) { if(!(abs(numbers[i] - numbers[j]) >= threshold)) return false; } return true; })())) return false; } return true; })())
        """
    assert match_postcondition(transformed, expected)

    # Test case 21: Test forall
    postcondition = """(res_tmp.size() == n) &&
     FORALL(0, n, i, res_tmp[i] == n + 2 * i))"""
    transformed = convert_postcondition_to_cpp(postcondition)
    print(transformed)
    expected = """
    (!((res_tmp == true)) 
            || ([&]() { for(int i = 0; i < numbers.size() - 1; i++) { if(([&]() { for(int j = i + 1; j < numbers.size(); j++) { if(abs(numbers[i] - numbers[j]) < threshold) return true; } return false; })()) return true; } return false; })()) 
    && (!((res_tmp == false)) 
            || ([&]() { for(int i = 0; i < numbers.size() - 1; i++) { if(!(([&]() { for(int j = i + 1; j < numbers.size(); j++) { if(!(abs(numbers[i] - numbers[j]) >= threshold)) return false; } return true; })())) return false; } return true; })())
        """
    assert match_postcondition(transformed, expected)

    

    print("All test cases passed!")

# Run the tests
if __name__ == "__main__":
    test_convert_postcondition_to_cpp()
