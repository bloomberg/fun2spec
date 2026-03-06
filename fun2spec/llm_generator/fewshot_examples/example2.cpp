// Copyright 2024 Bloomberg Finance L.P.
// Distributed under the terms of the MIT license.

#include <square.h>

Square* get_square(const int x)
// Return a pointer to a new Square object with side x
{
    Square * sqr_ptr = new Square(x);
    return sqr_ptr;
}