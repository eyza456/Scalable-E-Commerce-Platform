FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY proxy.inc /etc/nginx/proxy.inc

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1
