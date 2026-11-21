/* SPDX-License-Identifier: MIT */
#include "s3_gateway_session.h"

/* The real AP gate is born locked, epoch 1 at startup.  Wi-Fi STA
 * Connected may occur BEFORE AP workers start; do not drop that event.
 * The initialized word contains no permission flags, so never auto-arms.
 */
static s3_gateway_session_t device_session = { .word = (1u << 8) };
s3_gateway_session_t *s3_gateway_session_device(void)
{
    return &device_session;
}

#define S3_SESSION_EPOCH_SHIFT 8u
#define S3_SESSION_EPOCH_LIMIT 0x00ffffffu
#define S3_SESSION_KEEP_ON_REVOKE (S3_SESSION_STA | S3_SESSION_AP)
#define S3_SESSION_FLAG_MASK 0x7fu

static uint32_t get(const s3_gateway_session_t *s)
{
    return s ? __atomic_load_n(&s->word, __ATOMIC_ACQUIRE) : 0;
}
static uint32_t epoch_of(uint32_t word) { return word >> S3_SESSION_EPOCH_SHIFT; }
static uint32_t flags_of(uint32_t word) { return word & S3_SESSION_FLAG_MASK; }

void s3_gateway_session_init(s3_gateway_session_t *s)
{
    if (s) __atomic_store_n(&s->word, (uint32_t)(1u << S3_SESSION_EPOCH_SHIFT),
                            __ATOMIC_RELEASE);
}
uint32_t s3_gateway_session_epoch(const s3_gateway_session_t *s)
{
    return epoch_of(get(s));
}
uint32_t s3_gateway_session_flags(const s3_gateway_session_t *s)
{
    return flags_of(get(s));
}

bool s3_gateway_session_event(s3_gateway_session_t *s,
                              s3_gateway_session_event_t event)
{
    if (!s) return false;
    uint32_t old, next, flags, epoch;
    do {
        old = get(s);
        epoch = epoch_of(old);
        if (!epoch) return false; /* Uninitialized / exhausted: locked off. */
        flags = flags_of(old);
        bool revoke = false;
        switch (event) {
        case S3_SESSION_STA_ONLINE:
            flags |= S3_SESSION_STA;
            break;
        case S3_SESSION_AP_READY:
            flags |= S3_SESSION_AP;
            break;
        case S3_SESSION_DNS_LISTENER_READY:
            if (!(flags & S3_SESSION_AP)) return false;
            flags |= S3_SESSION_DNS;
            break;
        case S3_SESSION_TCP_LISTENER_READY:
            if (!(flags & S3_SESSION_AP)) return false;
            flags |= S3_SESSION_TCP;
            break;
        case S3_SESSION_OUTPUT_HOOK_READY:
            if ((flags & (S3_SESSION_AP | S3_SESSION_TCP)) !=
                (S3_SESSION_AP | S3_SESSION_TCP)) return false;
            flags |= S3_SESSION_HOOK;
            break;
        case S3_SESSION_STA_LOST:
            flags &= ~S3_SESSION_STA;
            revoke = true;
            break;
        case S3_SESSION_AP_LOST:
            flags &= ~S3_SESSION_AP;
            revoke = true;
            break;
        case S3_SESSION_NODE_FAILED:
        case S3_SESSION_WORKER_FAILED:
        case S3_SESSION_ADMIN_OFF:
            revoke = true;
            break;
        case S3_SESSION_CONFIG_ENTER:
            flags = 0;
            revoke = true;
            break;
        default:
            return false;
        }
        if (revoke) {
            /* No stale worker can re-arm after a failure/reconnect. */
            flags &= S3_SESSION_KEEP_ON_REVOKE;
            if (epoch == S3_SESSION_EPOCH_LIMIT) next = 0;
            else next = ((epoch + 1u) << S3_SESSION_EPOCH_SHIFT) | flags;
        } else {
            next = (epoch << S3_SESSION_EPOCH_SHIFT) | flags;
        }
        if (next == old) return true;
    } while (!__atomic_compare_exchange_n(&s->word, &old, next, false,
                                           __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return true;
}

bool s3_gateway_session_node_proven(s3_gateway_session_t *s,
                                    uint32_t started_epoch)
{
    if (!s || !started_epoch) return false;
    uint32_t old, next, flags;
    do {
        old = get(s);
        if (epoch_of(old) != started_epoch) return false;
        flags = flags_of(old);
        if ((flags & (S3_SESSION_STA | S3_SESSION_AP)) !=
            (S3_SESSION_STA | S3_SESSION_AP)) return false;
        next = old | S3_SESSION_NODE;
        if (next == old) return true;
    } while (!__atomic_compare_exchange_n(&s->word, &old, next, false,
                                           __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return true;
}

bool s3_gateway_session_admin_arm(s3_gateway_session_t *s,
                                  uint32_t verified_epoch)
{
    if (!s || !verified_epoch) return false;
    uint32_t old, next;
    do {
        old = get(s);
        if (epoch_of(old) != verified_epoch ||
            (flags_of(old) & S3_SESSION_PREREQS) != S3_SESSION_PREREQS)
            return false;
        next = old | S3_SESSION_ARMED;
        if (next == old) return true;
    } while (!__atomic_compare_exchange_n(&s->word, &old, next, false,
                                           __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return true;
}

bool s3_gateway_session_ready(const s3_gateway_session_t *s)
{
    uint32_t word = get(s);
    return epoch_of(word) != 0 &&
           (flags_of(word) & (S3_SESSION_PREREQS | S3_SESSION_ARMED)) ==
           (S3_SESSION_PREREQS | S3_SESSION_ARMED);
}
