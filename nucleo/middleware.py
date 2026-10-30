from django.shortcuts import redirect

class AdminLoginRedirectMiddleware:
    """Middleware para redirecionar tentativas de login no admin para a view personalizada"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Se o usuário já está autenticado e tenta acessar o admin, permite a requisição
        if request.path.endswith("/admin/login/"):
            return redirect("login")

        # Permite que o request continue normalmente
        response = self.get_response(request)
        return response
