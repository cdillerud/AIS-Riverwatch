FROM node:20-alpine

WORKDIR /app

# Accept build argument for backend URL
ARG REACT_APP_BACKEND_URL=http://localhost:8001
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package.json ./
RUN yarn install || true

COPY . .

EXPOSE 3000

CMD ["yarn", "start"]
