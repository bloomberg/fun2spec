# Copyright 2024 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from dataclasses import dataclass
import re
from typing import Optional
from llm_generator.postcondition import convert_postcondition_to_cpp

@dataclass
class Postcondition:
    """
    postcondition as a string with reasoning and probability according to the LLM
    """
    predicate: str
    reasoning: str
    prob: float

    # call convert_postcondition_to_cpp
    def get_cpp_expression(self):
        if "==>" in self.predicate or "FORALL" in self.predicate or "EXISTS" in self.predicate:
            return convert_postcondition_to_cpp(self.predicate)
        return self.predicate

def extract_reasoning(cd: str) -> Optional[str]:
    try:
        reasoning: str = re.search(r'Reasoning:((.|\n)*)Post', cd).group(1)
        reasoning = reasoning.lstrip('\n')
    except:
        reasoning = None
    return reasoning

def extract_postcondition(text):
    """Extracts the postcondition from a string without using regular expressions."""

    start_index = text.find("POST(")
    if start_index == -1:
        return None  # "POST(" not found

    start_index += 5  # Move past "POST("
    balance = 1
    end_index = start_index

    while end_index < len(text):
        if text[end_index] == '(':
            balance += 1
        elif text[end_index] == ')':
            balance -= 1
        if balance == 0:
            return text[start_index:end_index].strip()  # Return substring
        end_index += 1
    
    return None  # Unbalanced parentheses

# Run the tests
if __name__ == "__main__":
    # Example usage:
    text1 = """
    POST(res_tmp: (res_tmp.size() == n) &&
        FORALL(0, n, i, res_tmp[i] == n + 2 * i))
    Some arbitrary text here.
    More text
    """

    text2 = """
    Some text
    POST(another_condition)
    more text
    """

    text3 = """
    Invalid POST( condition
    """

    text4 = """POST(a)
    POST(b)
    """

    print(f"Text 1 Postcondition: {extract_postcondition(text1)}")
    print(f"Text 2 Postcondition: {extract_postcondition(text2)}")
    print(f"Text 3 Postcondition: {extract_postcondition(text3)}")
    print(f"Text 4 Postcondition: {extract_postcondition(text4)}")
