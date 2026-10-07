FROM magicbane/magicbox@sha256:20050d2a9a1e59deb83a270f78e5cd2111c5fc0a786651de0f0c1c39c56214a2
USER mbbox
WORKDIR /home/mbbox/magicbane
COPY --chown=mbbox:mbbox build-inputs.sha256 /opt/shadowbane/
RUN --network=none --mount=type=bind,from=server-source,target=/reviewed-source,ro \
    test "$(git -C build/Server rev-parse HEAD)" = "bafb48fe14e5356a64137954cf2d79205835a204" \
    && git -C build/Server diff --quiet \
    && git -C build/Server diff --cached --quiet \
    && sha256sum --check /opt/shadowbane/build-inputs.sha256 \
    && git -C build/Server bundle verify /reviewed-source/source.bundle \
    && git -C build/Server fetch --no-tags /reviewed-source/source.bundle HEAD \
    && test "$(git -C build/Server rev-parse FETCH_HEAD)" = "65952a25afe3fc86cb4cf23a5ff375d1b2f854b5" \
    && git -C build/Server checkout --detach 65952a25afe3fc86cb4cf23a5ff375d1b2f854b5 \
    && test "$(git -C build/Server rev-parse 'HEAD^{tree}')" = "173a4699d597b8cf0e4bec933b669545839d55ea" \
    && git -C build/Server diff --quiet \
    && git -C build/Server diff --cached --quiet \
    && test "$(find build/Server/src -name '*.java' | wc -l)" -eq 821 \
    && ant -buildfile build/build.xml \
    && test "$(find build/classes -name '*.class' | wc -l)" -eq 970 \
    && tar -xzf mb.data/heightmaps.tar.gz -C mb.data \
    && { git -C build/Server rev-parse HEAD 'HEAD^{tree}'; sha256sum build/bin/magicbane.jar mb.data/magicbane.sql; } > /opt/shadowbane/build-receipt.txt
COPY --chown=mbbox:mbbox entrypoint.sh healthcheck.sh credential-smoke.sh CredentialLoggingSmoke.java bloodline-costs.sql /opt/shadowbane/
RUN sha256sum /opt/shadowbane/bloodline-costs.sql >> /opt/shadowbane/build-receipt.txt \
    && bash -n /opt/shadowbane/entrypoint.sh \
    && bash -n /opt/shadowbane/healthcheck.sh \
    && bash -n /opt/shadowbane/credential-smoke.sh \
    && bash /opt/shadowbane/credential-smoke.sh
LABEL org.opencontainers.image.source="https://github.com/best-coder-open-now-near-me/shadowbane-server" \
      org.opencontainers.image.revision="65952a25afe3fc86cb4cf23a5ff375d1b2f854b5" \
      org.shadowbane.source-tree="173a4699d597b8cf0e4bec933b669545839d55ea"
ENTRYPOINT ["/bin/bash", "/opt/shadowbane/entrypoint.sh"]
CMD []
