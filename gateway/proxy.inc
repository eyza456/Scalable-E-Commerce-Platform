# Mantener metodo, cuerpo y query string, retirando solamente el prefijo /api.
rewrite ^/api(/.*)$ $1 break;
proxy_pass http://$backend;
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $http_host;
proxy_set_header Authorization $http_authorization;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $http_host;
proxy_set_header X-Forwarded-Prefix /api;
proxy_set_header X-Request-ID $request_id;
proxy_set_header X-Internal-Service-Key "";
proxy_connect_timeout 3s;
proxy_send_timeout 30s;
proxy_read_timeout 30s;
proxy_cache off;
proxy_intercept_errors off;

# No repetir automaticamente operaciones de compra ante una respuesta incierta.
proxy_next_upstream off;

# FastAPI puede canonicalizar una barra final. El cliente conserva /api y su
# host/puerto externo, en lugar de recibir una URL interna del contenedor.
proxy_redirect ~^https?://[^/]+(/.*)$ /api$1;
proxy_redirect ~^(/.*)$ /api$1;
