# !/bin/sh
# ############################################################################ #
#                              MAINTENANCE HISTORY                             #
# ############################################################################ #
# DATE         Description
# ------------ -----------------------------------------------------------------
# 08-MAY-2025  Initial Draft
# ============================================================================ #

# ============================= GLOBAL VARIABLES ============================= #

# ================================= CONSTANTS ================================ #
DBFile="$Db/db.sqlite3"

# ================================= FUNCTIONS ================================ #

# =================================== MAIN =================================== #

LogInitFnct "Database"
LogFnct "DEBUG" "`basename $0` initializing..."

display_usage() {
    echo "`basename $0` Usage:"
    echo "0: List Tables"
    echo "1: Dump data from <Table Number>"
    echo "2: Truncate <Table Number>"
}

if [ $# -lt 1 ] || [ $# -gt 2 ]
then
    display_usage
    sqlite3 $DBFile .tables | tr -s [:blank:] '\n' | nl
    exit 1
fi

if [ "$1" = "0" ]
then
    sqlite3 $DBFile .tables | tr -s [:blank:] '\n' | nl

elif [ "$1" = "1" ]
then
    TableIndex="$2"

    if [ -z "$TableIndex" ]; then
        LogFnct "ERROR" "Invalid table index: $TableIndex"
        exit 3
    fi

    TableList=$(sqlite3 "$DBFile" .tables | tr -s '[:blank:]' '\n')
    Table=$(echo "$TableList" | sed -n "${TableIndex}p")

    if [ -z "$Table" ]; then
        LogFnct "ERROR" "Invalid table index: $TableIndex"
        exit 2
    fi

    Columns=$(sqlite3 "$DBFile" "PRAGMA table_info(${Table});" | cut -d'|' -f2)
    sqlite3 -header $DBFile "SELECT * FROM $Table;" > "$Data/$Table.tsv"

    LogFnct "DEBUG" "Dumped table '$Table' to '$Data/$Table.tsv'"

elif [ "$1" = "2" ]
then
    TableIndex="$2"

    if [ -z "$TableIndex" ]; then
        LogFnct "ERROR" "Invalid table index: $TableIndex"
        exit 3
    fi

    TableList=$(sqlite3 "$DBFile" .tables | tr -s '[:blank:]' '\n')
    Table=$(echo "$TableList" | sed -n "${TableIndex}p")

    if [ -z "$Table" ]; then
        LogFnct "ERROR" "Invalid table index: $TableIndex"
        exit 3
    fi

    sqlite3 "$DBFile" "DELETE FROM $Table;"
    sqlite3 "$DBFile" "DELETE FROM sqlite_sequence WHERE name='$Table';"
    LogFnct "INFO" "Truncated table '$Table'"
fi
