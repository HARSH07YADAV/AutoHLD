.PHONY: run stop restart logs clean

run:
	docker-compose up --build -d
	docker-compose exec ollama ollama pull qwen2.5:1.5b

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f autohld

clean:
	docker-compose down -v
