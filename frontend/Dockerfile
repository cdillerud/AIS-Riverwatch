FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=development

ARG REACT_APP_BACKEND_URL=http://34.172.47.153:8001
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package.json ./
COPY yarn.lock* package-lock.json* ./

RUN if [ -f yarn.lock ]; then \
      yarn install --frozen-lockfile --production=false; \
    elif [ -f package-lock.json ]; then \
      npm ci --include=dev; \
    else \
      yarn install --production=false; \
    fi

COPY . .

EXPOSE 3000

CMD ["yarn", "start"]
