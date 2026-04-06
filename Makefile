.PHONY: help install dev test lint format clean docker-up docker-down docker-build docker-logs

# 默认目标
.DEFAULT_GOAL := help

# 颜色定义
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# 帮助信息
help:
	@echo "$(BLUE)全智能量化交易系统 - 开发工具$(NC)"
	@echo ""
	@echo "$(YELLOW)可用命令:$(NC)"
	@echo "  $(GREEN)make install$(NC)      - 安装开发依赖"
	@echo "  $(GREEN)make dev$(NC)         - 安装开发环境"
	@echo "  $(GREEN)make test$(NC)        - 运行所有测试"
	@echo "  $(GREEN)make test-unit$(NC)   - 运行单元测试"
	@echo "  $(GREEN)make test-integration$(NC) - 运行集成测试"
	@echo "  $(GREEN)make test-e2e$(NC)    - 运行端到端测试"
	@echo "  $(GREEN)make lint$(NC)        - 运行代码检查"
	@echo "  $(GREEN)make format$(NC)      - 格式化代码"
	@echo "  $(GREEN)make type-check$(NC)  - 运行类型检查"
	@echo "  $(GREEN)make security$(NC)    - 运行安全检查"
	@echo "  $(GREEN)make clean$(NC)       - 清理构建文件"
	@echo "  $(GREEN)make docker-up$(NC)   - 启动Docker服务"
	@echo "  $(GREEN)make docker-down$(NC) - 停止Docker服务"
	@echo "  $(GREEN)make docker-build$(NC) - 构建Docker镜像"
	@echo "  $(GREEN)make docker-logs$(NC) - 查看Docker日志"
	@echo "  $(GREEN)make migrate$(NC)     - 运行数据库迁移"
	@echo "  $(GREEN)make run$(NC)         - 运行开发服务器"
	@echo "  $(GREEN)make coverage$(NC)    - 生成测试覆盖率报告"
	@echo ""

# 安装依赖
install:
	@echo "$(BLUE)安装项目依赖...$(NC)"
	pip install -e ".[dev,test,prod]"

# 开发环境设置
dev: install
	@echo "$(BLUE)设置开发环境...$(NC)"
	pre-commit install
	cp .env.example .env
	@echo "$(GREEN)开发环境设置完成！$(NC)"
	@echo "请编辑 .env 文件配置环境变量"

# 运行测试
test:
	@echo "$(BLUE)运行所有测试...$(NC)"
	pytest -v

test-unit:
	@echo "$(BLUE)运行单元测试...$(NC)"
	pytest -m unit -v

test-integration:
	@echo "$(BLUE)运行集成测试...$(NC)"
	pytest -m integration -v

test-e2e:
	@echo "$(BLUE)运行端到端测试...$(NC)"
	pytest -m e2e -v

# 代码检查
lint:
	@echo "$(BLUE)运行代码检查...$(NC)"
	flake8 src tests
	black --check src tests
	isort --check-only src tests
	mypy src
	bandit -r src -c pyproject.toml

# 代码格式化
format:
	@echo "$(BLUE)格式化代码...$(NC)"
	black src tests
	isort src tests

# 类型检查
type-check:
	@echo "$(BLUE)运行类型检查...$(NC)"
	mypy src

# 安全检查
security:
	@echo "$(BLUE)运行安全检查...$(NC)"
	safety check
	bandit -r src -c pyproject.toml
	@echo "$(BLUE)扫描依赖漏洞...$(NC)"
	pip-audit

# 清理
clean:
	@echo "$(BLUE)清理构建文件...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml .pytest_cache .mypy_cache htmlcov

# Docker命令
docker-up:
	@echo "$(BLUE)启动Docker服务...$(NC)"
	docker-compose up -d

docker-down:
	@echo "$(BLUE)停止Docker服务...$(NC)"
	docker-compose down

docker-build:
	@echo "$(BLUE)构建Docker镜像...$(NC)"
	docker-compose build

docker-logs:
	@echo "$(BLUE)查看Docker日志...$(NC)"
	docker-compose logs -f

# 数据库迁移
migrate:
	@echo "$(BLUE)运行数据库迁移...$(NC)"
	alembic upgrade head

migrate-create:
	@echo "$(BLUE)创建新的迁移文件...$(NC)"
	@read -p "请输入迁移描述: " desc; \
	alembic revision --autogenerate -m "$$desc"

# 运行开发服务器
run:
	@echo "$(BLUE)启动开发服务器...$(NC)"
	./start_production.sh simulation

# 覆盖率报告
coverage:
	@echo "$(BLUE)生成测试覆盖率报告...$(NC)"
	pytest --cov=src --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)覆盖率报告已生成，打开 htmlcov/index.html 查看$(NC)"

# 预提交检查
pre-commit:
	@echo "$(BLUE)运行预提交检查...$(NC)"
	pre-commit run --all-files

# 依赖更新
update-deps:
	@echo "$(BLUE)更新依赖...$(NC)"
	pip install --upgrade pip
	pip install -U -r requirements.txt
	pip install -U -r requirements-dev.txt
	pip install -U -r requirements-test.txt
	pip install -U -r requirements-prod.txt

# 生成依赖图
deps-graph:
	@echo "$(BLUE)生成依赖关系图...$(NC)"
	pipdeptree --graph-output png > deps.png
	@echo "$(GREEN)依赖关系图已保存为 deps.png$(NC)"

# 性能分析
profile:
	@echo "$(BLUE)性能分析...$(NC)"
	python -m cProfile -o profile.prof src/main.py
	@echo "$(GREEN)性能分析文件已保存为 profile.prof$(NC)"
	@echo "使用 snakeviz profile.prof 查看分析结果"

# 文档生成
docs:
	@echo "$(BLUE)生成API文档...$(NC)"
	pdoc --html --output-dir docs/api src
	@echo "$(GREEN)API文档已生成到 docs/api 目录$(NC)"

# 备份数据库
backup:
	@echo "$(BLUE)备份数据库...$(NC)"
	docker-compose exec postgres pg_dumpall -U trader | gzip > backup/$(shell date +%Y%m%d_%H%M%S).sql.gz
	@echo "$(GREEN)数据库备份完成$(NC)"

# 恢复数据库
restore:
	@echo "$(BLUE)恢复数据库...$(NC)"
	@read -p "请输入备份文件路径: " file; \
	gunzip -c $$file | docker-compose exec -T postgres psql -U trader
	@echo "$(GREEN)数据库恢复完成$(NC)"

# 监控
monitor:
	@echo "$(BLUE)启动监控...$(NC)"
	@echo "$(YELLOW)Prometheus: http://localhost:9090$(NC)"
	@echo "$(YELLOW)Grafana: http://localhost:3000 (admin/admin123)$(NC)"
	@echo "$(YELLOW)Kibana: http://localhost:5601$(NC)"
	docker-compose up -d prometheus grafana elasticsearch logstash kibana

# 健康检查
health:
	@echo "$(BLUE)检查服务健康状态...$(NC)"
	@echo "$(YELLOW)应用:$(NC)"
	curl -f http://localhost:8000/health || echo "$(RED)应用不可用$(NC)"
	@echo ""
	@echo "$(YELLOW)数据库:$(NC)"
	docker-compose exec postgres pg_isready -U trader || echo "$(RED)数据库不可用$(NC)"
	@echo ""
	@echo "$(YELLOW)Redis:$(NC)"
	docker-compose exec redis redis-cli ping || echo "$(RED)Redis不可用$(NC)"
	@echo ""
	@echo "$(YELLOW)监控:$(NC)"
	curl -f http://localhost:9090/-/healthy || echo "$(RED)Prometheus不可用$(NC)"
	curl -f http://localhost:3000/api/health || echo "$(RED)Grafana不可用$(NC)"