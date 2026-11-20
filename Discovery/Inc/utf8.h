#ifndef UTF8_H
#define UTF8_H

#include <stdint.h>

#define UTF8_REPLACEMENT_CHARACTER 0xFFFDu

/* Decode one NUL-terminated UTF-8 sequence.
 * Returns the number of consumed bytes (always at least one).
 * Invalid or truncated input consumes one byte and returns U+FFFD. */
uint8_t utf8_decode(const char *text, uint32_t *codepoint);

#endif /* UTF8_H */
