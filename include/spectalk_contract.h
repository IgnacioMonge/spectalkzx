/*
 * spectalk_contract.h - Shared resident/overlay constants.
 *
 * Pure preprocessor contract only: no z88dk headers, structs, prototypes,
 * globals, or declarations that can pull resident dependencies into overlays.
 */

#ifndef SPECTALK_CONTRACT_H
#define SPECTALK_CONTRACT_H

#define VERSION "1.4.2"

#define RING_BUFFER_SIZE 2048
#define RING_BUFFER_MASK (RING_BUFFER_SIZE - 1)
#define LINE_BUFFER_SIZE 128
#define RX_LINE_SIZE 512
#define OVERLAY_SLOT_SIZE RX_LINE_SIZE

#define IRC_SERVER_SIZE   32
#define IRC_PORT_SIZE      6
#define IRC_NICK_SIZE     18
#define IRC_PASS_SIZE     24
#define AUTH_SERVICE_SIZE 32
#define AUTH_COMMAND_SIZE 64
#define AUTH_LEGACY        0
#define AUTH_PENDING       1
#define AUTH_LEARNED       2
#define AUTH_SAVE          3

/* Bookmark startup selection; inferred legacy UI marks are never persisted. */
#define BOOKMARK_SLOT_MASK 0x3F
#define BOOKMARK_INFERRED  0x40

#define AUTOJOIN_MOTD_DONE   0x01
#define AUTOJOIN_IDENT_WAIT  0x02
#define AUTOJOIN_IDENT_SENT  0x04
#define USER_MODE_SIZE     6
#define NETWORK_NAME_SIZE 12
#define NAMES_TARGET_CHANNEL_SIZE 32
#define SEARCH_PATTERN_SIZE       64

#define MAX_FRIENDS 5
#define MAX_IGNORES 5

/* Connection state values shared by resident code and status overlays. */
#define STATE_DISCONNECTED  0
#define STATE_WIFI_OK       1
#define STATE_TCP_CONNECTED 2
#define STATE_IRC_READY     3

/* Channel table contract: each entry is 32B and flags are at byte 30. */
#define MAX_CHANNELS         10
#define CH_SIZE              32
#define CH_FLAGS_OFF         30
#define CH_FLAG_ACTIVE       0x01
#define CH_FLAG_QUERY        0x02
#define CH_FLAG_UNREAD       0x04
#define CH_FLAG_MENTION      0x08
#define CH_FLAG_NAMING       0x10
#define CH_FLAG_COUNT_DIRTY  0x20

/* Timezone sentinel: user explicitly selected hardware RTC mode. */
#define TZ_RTC 127

/* UI overlay modes stored in overlay_mode. These are not atlas ids. */
#define OVERLAY_NONE      0
#define OVERLAY_HELP      1
#define OVERLAY_ABOUT     2
#define OVERLAY_CONFIG    3
#define OVERLAY_STATUS    4
#define OVERLAY_WHATSNEW  5
#define OVERLAY_BOOKMARKS 6

/* Theme attribute indices; must match theme_attrs[] layout. */
#define TATTR_BANNER     0
#define TATTR_STATUS     1
#define TATTR_MSG_CHAN   2
#define TATTR_MSG_SELF   3
#define TATTR_MSG_PRIV   4
#define TATTR_MAIN_BG    5
#define TATTR_INPUT      6
#define TATTR_PROMPT     8
#define TATTR_MSG_SYS    9
#define TATTR_MSG_JOIN  10
#define TATTR_MSG_NICK  11
#define TATTR_MSG_TIME  12
#define TATTR_MSG_TOPIC 13
#define TATTR_MSG_MOTD  14
#define TATTR_ERROR     15
#define TATTR_STATUS_RED    16
#define TATTR_STATUS_YELLOW 17
#define TATTR_STATUS_GREEN  18
#define TATTR_BORDER_COLOR  19

#endif /* SPECTALK_CONTRACT_H */
