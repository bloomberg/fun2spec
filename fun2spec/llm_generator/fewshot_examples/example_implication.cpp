// Copyright 2024 Bloomberg Finance L.P.
// Distributed under the terms of the MIT license.

// Returns the result of dividing numerator by denominator.
// If denominator is 0, returns -1 as an error code. 
int divide(int numerator, int denominator) { 
    
    if (denominator == 0) 
    { 
        return -1; 
    }
    
    return numerator / denominator; 
} 