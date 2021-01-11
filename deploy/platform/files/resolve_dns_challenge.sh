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

# braces protect from script file edits
{
    NP_CHALLENGE_PATH="$(dirname "$0")"
    NP_SECRET_PATH="$(dirname "$NP_CHALLENGE_PATH")/secret"
    NP_PLATFORM_TOKEN="$(cat "$NP_SECRET_PATH/token" | tr -d '[:space:]')"

    if [ -z "$NP_PLATFORM_CONFIG_URL" ]; then _error "NP_PLATFORM_CONFIG_URL is empty"; fi
    if [ -z "$NP_PLATFORM_TOKEN" ]; then _error "NP_PLATFORM_TOKEN is empty"; fi
    if [ -z "$NP_CLUSTER_NAME" ]; then _error "NP_CLUSTER_NAME is empty"; fi

    apk add -q --update --no-cache curl

    ACTION="$1"
    URL="$NP_PLATFORM_CONFIG_URL/api/v1/clusters/$NP_CLUSTER_NAME/dns/acme_challenge"
    PAYLOAD="{\"dns_name\": \"$2\", \"value\": \"$3\"}"

    if [ "$ACTION" == "present" ]; then
        _retry \
            3 \
            1 \
            _curl -X PUT \
                -H "Authorization: Bearer $NP_PLATFORM_TOKEN" \
                -d "$PAYLOAD" \
                "$URL"
    fi

    if [ "$ACTION" == "cleanup" ]; then
        _retry \
            3 \
            1 \
            _curl -X DELETE \
                -H "Authorization: Bearer $NP_PLATFORM_TOKEN" \
                -d "$PAYLOAD" \
                "$URL"
    fi

    exit 0
}
