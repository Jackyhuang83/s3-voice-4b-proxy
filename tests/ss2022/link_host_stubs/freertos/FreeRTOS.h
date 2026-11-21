#pragma once
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(ptr) ((void)(ptr))
#define portEXIT_CRITICAL(ptr) ((void)(ptr))
#define pdMS_TO_TICKS(ms) (ms)
