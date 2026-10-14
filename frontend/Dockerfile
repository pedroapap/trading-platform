FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./

# The optional `ca_bundle` build secret adds a CA bundle for builds behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=ca_bundle \
    if [ -f /run/secrets/ca_bundle ]; then \
        export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; \
    fi; \
    npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
