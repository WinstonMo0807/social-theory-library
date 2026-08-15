ARG BASE_IMAGE
FROM ${BASE_IMAGE}

USER root
WORKDIR /app
COPY --chown=node:node web/package.json web/package-lock.json ./
COPY offline/web-runtime-node-modules-2.5.0-linux-x64.tar.gz /tmp/web-runtime-node-modules.tar.gz
RUN rm -rf /app/node_modules \
    && tar -xzf /tmp/web-runtime-node-modules.tar.gz -C /app \
    && rm /tmp/web-runtime-node-modules.tar.gz \
    && chmod 0755 /app/node_modules/.bin/* \
    && chmod 0755 /app/node_modules/@esbuild/linux-x64/bin/esbuild \
    && chown -R node:node /app/node_modules
RUN rm -rf /app/dist
COPY --chown=node:node web/dist ./dist
COPY --chown=node:node web/scripts ./scripts
RUN rm -rf /app/public
COPY --chown=node:node web/public ./public
COPY web/docker-entrypoint.sh /usr/local/bin/library-web-entrypoint
RUN chmod 0755 /usr/local/bin/library-web-entrypoint
USER node
ENTRYPOINT ["/usr/local/bin/library-web-entrypoint"]
CMD ["npm", "run", "start"]
