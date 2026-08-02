FROM postgres:18-alpine

RUN apk add --no-cache bash curl restic

COPY deployment/backup/run.sh /usr/local/bin/citeguild-backup
RUN chmod 0755 /usr/local/bin/citeguild-backup

USER postgres

ENTRYPOINT ["/usr/local/bin/citeguild-backup"]
