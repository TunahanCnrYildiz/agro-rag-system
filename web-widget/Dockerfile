# Static demo site + embeddable widget script, served by nginx.
#
# site/index.html loads the widget from the absolute path /widget/agro-chat-widget.js
# (see the <script> tag at the bottom of site/index.html), so both directories are
# copied to preserve that layout.
FROM nginx:1.27-alpine

COPY site/ /usr/share/nginx/html/
COPY widget/ /usr/share/nginx/html/widget/
COPY docker-entrypoint.d/10-api-base.sh /docker-entrypoint.d/10-api-base.sh
RUN chmod +x /docker-entrypoint.d/10-api-base.sh

EXPOSE 80
