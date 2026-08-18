FROM node:24-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build
RUN npm prune --omit=dev --ignore-scripts && npm cache clean --force

FROM node:24-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY --chown=node:node --from=build /app/package.json /app/package-lock.json ./
COPY --chown=node:node --from=build /app/node_modules ./node_modules
COPY --chown=node:node --from=build /app/dist ./dist
COPY --chown=node:node --from=build /app/.openai ./.openai
COPY --chown=node:node --from=build /app/scripts ./scripts
COPY --chown=node:node --from=build /app/public ./public
COPY docker-entrypoint.sh /usr/local/bin/library-web-entrypoint
RUN chmod 0755 /usr/local/bin/library-web-entrypoint
USER node
EXPOSE 3000
ENTRYPOINT ["/usr/local/bin/library-web-entrypoint"]
CMD ["npm", "run", "start"]
