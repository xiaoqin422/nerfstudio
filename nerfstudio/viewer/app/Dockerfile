FROM node:18.16-bullseye-slim

WORKDIR /nerf

COPY . .

RUN ls -l && npm -v && yarn install && yarn build

EXPOSE 4000


CMD ["/bin/bash"]