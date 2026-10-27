# Both digests are linux/amd64 images. Never compile against a developer host ABI.
FROM public.ecr.aws/sam/build-python3.12@sha256:515ec163a8d73c04533ac8ee1d04ce67d5d6a4a5a3f870a36205eee18ebae7d0 AS build
ENV PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1704067200 LC_ALL=C TZ=UTC TMPDIR=/work/scratch
WORKDIR /work
RUN mkdir -p /work/scratch
COPY deployment/package/ /work/tooling/
RUN python3 -B /work/tooling/build_dds.py
RUN python3 -B -m pip download --disable-pip-version-check --no-cache-dir \
    --only-binary=:all: --platform manylinux2014_x86_64 \
    --implementation cp --python-version 3.12 --abi cp312 --abi abi3 \
    --require-hashes --requirement /work/tooling/requirements.lock --dest /work/wheels
RUN python3 -B -m pip install --disable-pip-version-check --no-cache-dir \
    --no-index --find-links=/work/wheels --only-binary=:all: --require-hashes \
    --no-compile --requirement /work/tooling/requirements.lock --target /work/dependencies
COPY lambdas/ /work/source/lambdas/
COPY staging_runtime.py /work/source/staging_runtime.py
COPY deployment/runtime-routes.json /work/source/deployment/runtime-routes.json
COPY deployment/package/requirements.lock deployment/package/native-source.json deployment/package/build_dds.py deployment/package/staging.Dockerfile /work/source/deployment/package/
RUN python3 -B /work/tooling/build_zip.py --source /work/source \
    --dependencies /work/dependencies --native /work/native --output /work/artifacts

FROM public.ecr.aws/lambda/python@sha256:c73d459e2dcaefa83c47c095560ad164d732251312b3371c7a49c46f1c4d4ff5 AS verify
ENV PYTHONDONTWRITEBYTECODE=1
COPY --from=build /work/artifacts/ /artifacts/
COPY deployment/package/verify_package.py /verify/verify_package.py
WORKDIR /var/task
RUN python3 -B /verify/verify_package.py --artifacts /artifacts --extract-to /var/task

FROM scratch AS export
COPY --from=verify /artifacts/ /
