FROM nousresearch/hermes-agent:v0.23.2@sha256:d6746a084e9341baada483e3d6210444d3c1aeb7c130f0915150065fb2851459

COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/hermes-railway-entrypoint

ENV HERMES_HOME=/data/.hermes \
    HERMES_WRITE_SAFE_ROOT=/data/.hermes \
    HERMES_LAZY_INSTALL_TARGET=/data/.hermes/lazy-packages \
    HERMES_DASHBOARD=1 \
    HERMES_DASHBOARD_HOST=0.0.0.0 \
    HERMES_GATEWAY_BOOTSTRAP_STATE=running

ENTRYPOINT ["/usr/local/bin/hermes-railway-entrypoint"]
CMD ["gateway", "run"]
