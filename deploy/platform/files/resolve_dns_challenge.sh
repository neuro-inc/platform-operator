#!/bin/sh

set -o errexit
set -o pipefail

function _error {
    echo "$1"
    return 1
}

function _retry {
    set +o errexit

    MAX_RETRIES="$1"
    RETRY_INTERVAL="$2"
    N=0

    shift
    shift

    while [ $N -lt "$MAX_RETRIES" ]; do
        LAST_RESULT="$("${@}")"
        RETURN_CODE=$?

        if [ "$RETURN_CODE" == 0 ]; then
            break
        fi

        N=$((N + 1))
        sleep "$RETRY_INTERVAL"
    done

    set -o errexit

    if [ ! -z "$LAST_RESULT" ]; then
        echo "$LAST_RESULT"
    fi

    return ${RETURN_CODE:-1}
}

function _curl {
    RESPONSE_FILE="$(mktemp "/tmp/response.XXXXXX")"
    HTTP_CODE="$(curl -sL -o "$RESPONSE_FILE" -w "%{http_code}" "$@")"

    if [ "$HTTP_CODE" -ge "400" ]; then
        echo "http code: $HTTP_CODE, response: $(cat "$RESPONSE_FILE")"
        RETURN_CODE=1
    else
        RETURN_CODE=0
    fi

    rm "$RESPONSE_FILE"

    return ${RETURN_CODE:-1}
}

if [ -z "$NP_PLATFORM_API_URL" ]; then _error "NP_PLATFORM_API_URL is empty"; fi
if [ -z "$NP_CLUSTER_TOKEN" ]; then _error "NP_CLUSTER_TOKEN is empty"; fi
if [ -z "$NP_CLUSTER_NAME" ]; then _error "NP_CLUSTER_NAME is empty"; fi

apk add -q --update --no-cache curl

ACTION="$1"
DNS_NAME="$2"
VALUE="$3"
PLATFORM_API_PATH="clusters/$NP_CLUSTER_NAME/dns/acme_challenge"
PAYLOAD="$(cat <<EOM
{
    "dns_name": "$DNS_NAME",
    "value": "$VALUE"
}
EOM
)"

if [ "$ACTION" == "present" ]; then
    _retry \
        3 \
        1 \
        _curl -X PUT \
            -H "Authorization: Bearer $NP_CLUSTER_TOKEN" \
            -d "$PAYLOAD" \
            "$NP_PLATFORM_API_URL/$PLATFORM_API_PATH"
fi

if [ "$ACTION" == "cleanup" ]; then
    _retry \
        3 \
        1 \
        _curl -X DELETE \
            -H "Authorization: Bearer $NP_CLUSTER_TOKEN" \
            -d "$PAYLOAD" \
            "$NP_PLATFORM_API_URL/$PLATFORM_API_PATH"
fi
