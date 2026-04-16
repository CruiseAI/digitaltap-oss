FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY digitaltap/ digitaltap/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["digitaltap"]
CMD ["scan", "--demo"]
