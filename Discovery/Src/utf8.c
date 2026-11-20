#include "utf8.h"

static uint8_t utf8_is_continuation(uint8_t byte)
{
    return (byte & 0xC0u) == 0x80u;
}

uint8_t utf8_decode(const char *text, uint32_t *codepoint)
{
    const uint8_t *bytes = (const uint8_t *)text;
    uint32_t value;
    uint8_t length;
    uint8_t index;

    if(bytes[0] < 0x80u)
    {
        *codepoint = bytes[0];
        return 1;
    }

    if((bytes[0] >= 0xC2u) && (bytes[0] <= 0xDFu))
    {
        value = bytes[0] & 0x1Fu;
        length = 2;
    }
    else if((bytes[0] >= 0xE0u) && (bytes[0] <= 0xEFu))
    {
        value = bytes[0] & 0x0Fu;
        length = 3;
    }
    else if((bytes[0] >= 0xF0u) && (bytes[0] <= 0xF4u))
    {
        value = bytes[0] & 0x07u;
        length = 4;
    }
    else
    {
        *codepoint = UTF8_REPLACEMENT_CHARACTER;
        return 1;
    }

    for(index = 1; index < length; index++)
    {
        if(!utf8_is_continuation(bytes[index]))
        {
            *codepoint = UTF8_REPLACEMENT_CHARACTER;
            return 1;
        }
        value = (value << 6) | (bytes[index] & 0x3Fu);
    }

    if(((length == 3) && (value < 0x800u)) ||
       ((length == 4) && (value < 0x10000u)) ||
       ((value >= 0xD800u) && (value <= 0xDFFFu)) ||
       (value > 0x10FFFFu))
    {
        *codepoint = UTF8_REPLACEMENT_CHARACTER;
        return 1;
    }

    *codepoint = value;
    return length;
}
