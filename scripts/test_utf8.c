#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "utf8.h"

static void check(const char *text, uint32_t expected, uint8_t length)
{
    uint32_t actual = 0;
    uint8_t consumed = utf8_decode(text, &actual);
    assert(actual == expected);
    assert(consumed == length);
}

int main(void)
{
    check("A", 0x41, 1);
    check("\xC3\xA7", 0xE7, 2);
    check("\xE4\xB8\xAD", 0x4E2D, 3);
    check("\xF0\x9F\x98\x80", 0x1F600, 4);
    check("\xC0\x80", UTF8_REPLACEMENT_CHARACTER, 1);
    check("\xE0\x80\x80", UTF8_REPLACEMENT_CHARACTER, 1);
    check("\xED\xA0\x80", UTF8_REPLACEMENT_CHARACTER, 1);
    check("\xF4\x90\x80\x80", UTF8_REPLACEMENT_CHARACTER, 1);
    check("\xE4\xB8", UTF8_REPLACEMENT_CHARACTER, 1);
    check("\x80", UTF8_REPLACEMENT_CHARACTER, 1);
    puts("UTF-8 decoder tests passed");
    return 0;
}
