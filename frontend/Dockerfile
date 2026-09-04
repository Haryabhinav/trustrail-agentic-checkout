# NOTE: this runs Vite's dev server (HMR, unminified bundle) — correct for the documented
# local-dev/demo flow (see docker-compose.yml), NOT a production build. A real deployment
# should build a separate image: `npm run build` then serve the static `dist/` output via
# nginx or a similar lightweight static server, rather than running `vite dev` in a container.
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# node:20-alpine ships a non-root `node` user (uid 1000) by convention; use it instead of
# running the dev server as root.
RUN chown -R node:node /app
USER node

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
