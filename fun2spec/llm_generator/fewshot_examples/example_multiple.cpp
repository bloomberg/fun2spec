// Copyright 2024 Bloomberg Finance L.P.
// Distributed under the terms of the MIT license.

#include <stdlib.h>

int checkJSON(
    const char *inpJson,
    Shema* schema,          
    )
    // Parse the JSON and match the schema with provided schema.
    // Return 0 on success, and a non-zero value (with no effect on '*nextPos')
    // otherwise.
{
    if(inpJson == NULL)
    {
        return -1;
    }

    auto parseTree = parseJSON(inpJson);

    if (parseTree == NULL || matchSchema(parseTree, schema))
    {
        return -1;
    }

    return 0;
}
