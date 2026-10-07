FROM magicbane/magicbox@sha256:20050d2a9a1e59deb83a270f78e5cd2111c5fc0a786651de0f0c1c39c56214a2
USER mbbox
WORKDIR /home/mbbox/magicbane
RUN test "$(git -C build/Server rev-parse HEAD)" = "bafb48fe14e5356a64137954cf2d79205835a204" \
    && git -C build/Server diff --quiet \
    && git -C build/Server diff --cached --quiet \
    && ant -buildfile build/build.xml \
    && tar -xzf mb.data/heightmaps.tar.gz -C mb.data
COPY --chown=mbbox:mbbox entrypoint.sh healthcheck.sh /opt/shadowbane/
RUN bash -n /opt/shadowbane/entrypoint.sh && bash -n /opt/shadowbane/healthcheck.sh
LABEL org.opencontainers.image.source="https://repo.magicbane.com/MagicBane/Server" \
      org.opencontainers.image.revision="bafb48fe14e5356a64137954cf2d79205835a204"
ENTRYPOINT ["/bin/bash", "/opt/shadowbane/entrypoint.sh"]
CMD []
