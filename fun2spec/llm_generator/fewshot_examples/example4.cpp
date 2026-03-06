// Copyright 2024 Bloomberg Finance L.P.
// Distributed under the terms of the MIT license.

#include<stdio.h>
#include<vector> 
using namespace std; 

vector<int> intersperse(vector<int> numbers, int delimeter)
    /* 
    Insert a number \"delimeter\" between every two consecutive elements of input vector `numbers\" 
    >>> intersperse({}, 4) {} 
    >>> intersperse({1, 2, 3}, 4) {1, 4, 2, 4, 3} 
    */ 
{
    vector<int> out={}; 
    if (numbers.size()>0) 
        out.push_back(numbers[0]); 
    for (int i=1;i<numbers.size();i++) { 
        out.push_back(delimeter); 
        out.push_back(numbers[i]); 
    } 
return out; 
}
