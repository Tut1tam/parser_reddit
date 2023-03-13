from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.dispatch import receiver
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import user_passes_test, login_required
from django.contrib.auth.models import User
import logging
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db.models.signals import post_save
import asyncio

logging.basicConfig(level=logging.INFO)


from .functions_python.child_parser_db import *
from .functions_python.reddit_parser import *
from .functions_python.cambridge_parser import *
from .forms import RegisterUserForm, SupportForm, QuizFormset
from .models import *

title_list = []
dictionary_definition = []
dictionary_examples = []


# Decorator for views that checks that the user is anonymous, redirecting
def anonymous_required(function=None, redirect_url="index"):

    if not redirect_url:
        redirect_url = settings.LOGIN_REDIRECT_URL

    actual_decorator = user_passes_test(
        lambda u: u.is_anonymous, login_url=redirect_url
    )

    if function:
        return actual_decorator(function)
    return actual_decorator


# Adult section main page
def index(request):
    context = {
        "title_list": title_list,
        "dictionary_definition": dictionary_definition,
        "dictionary_examples": dictionary_examples,
    }
    if request.method == "POST":
        title_list.clear()
        dictionary_definition.clear()
        dictionary_examples.clear()
        word_input = str(request.POST["word_input"])
        cambridge_parser(word_input, dictionary_definition, dictionary_examples)
        asyncio.run(reddit_parser(word_input, title_list))
        context = {
            "title_list": title_list,
            "word_input": word_input,
            "dictionary_definition": dictionary_definition,
            "dictionary_examples": dictionary_examples,
        }
        return render(request, "parser_app/index.html", context)
    else:
        return render(request, "parser_app/index.html")


def get_word_input(word_input):
    return word_input


# Child section
def child_questions(request):
    context = {
        "title_list": title_list,
    }
    if request.method == "POST":
        title_list.clear()
        word_input = str(request.POST["word_input"])
        child_parser_db(word_input, title_list)
        context = {"title_list": title_list, "word_input": word_input}
        return render(request, "parser_app/child_questions.html", context)
    else:
        return render(request, "parser_app/child_questions.html")


# Help page
def support(request):
    if request.method == "POST":
        form = SupportForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data.get("email")
            subject = form.cleaned_data.get("subject")
            message = form.cleaned_data.get("message")
            image = form.cleaned_data.get("image")
            template = render_to_string(
                "parser_app/email_template.html",
                {
                    "email": email,
                    "subject": subject,
                    "message": message,
                    "image": image,
                },
            )
            plain_template = strip_tags(template)
            messages.success(
                request, ("Техподдержка ответит вам скоро по этому email: " + email)
            )
            email = EmailMultiAlternatives(
                subject,
                plain_template,
                settings.EMAIL_HOST_USER,
                [settings.EMAIL_HOST_USER],
            )
            email.attach_alternative(template, "text/html")
            email.send()
            return redirect("index")
    else:
        form = SupportForm()
    return render(request, "parser_app/support.html", {"form": form})


# Test section
def quiz_create(request):
    context = {
        "form": form,
    }
    if request.method == "GET":
        form = QuizFormset(request.GET or None)
    elif request.method == "POST":
        form = QuizFormset(request.POST)
        if form.is_valid():
            for form in form:
                question = form.cleaned_data.get("name")
                answer = form.cleaned_data.get("answer")
                if question and answer:
                    Quiz(question=question).save()
                    Quiz(answer=answer).save()
            return redirect("profile")
    return render(request, "parser_app/quiz_create.html", context)


# <----------------------------------->

# Registarion page
@anonymous_required
def register(request):
    if request.method == "POST":
        form = RegisterUserForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password1")
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, ("Вы зарегистрировались как " + username))
            return redirect("index")
    else:
        form = RegisterUserForm()
    return render(request, "parser_app/register.html", {"form": form})


# Login page
@anonymous_required
def login_user(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Вы вошли как " + username)
            return redirect("index")
        else:
            messages.warning(request, "Логин или пароль неверны")
            return render(request, "parser_app/login.html")
    else:
        return render(request, "parser_app/login.html")


# Logout redirect
@login_required(login_url="/")
def logout_user(request):
    logout(request)
    messages.warning(request, ("Вы вышли из аккаунта"))
    return redirect("index")


# Profile page
@login_required(login_url="/")
def profile(request):
    user_info = User.objects.all()
    context = {"user_info": user_info}
    return render(request, "parser_app/profile.html", context)


# Update profile page
@login_required(login_url="/")
def update_profile(request):
    user_info = User.objects.get(id=request.user.id)
    if request.method == "POST":
        form = RegisterUserForm(request.POST or None, instance=user_info)
        if form.is_valid():
            form.save()
            user_info.username = request.POST["username"]
            user_info.email = request.POST["email"]
            login(request, user_info)
            messages.success(request, "Данные успешно обновлены")
            return redirect("profile")
    else:
        form = RegisterUserForm(instance=user_info)
        del form.fields["group"]
    context = {"form": form}
    return render(request, "parser_app/update_profile.html", context)


# Assign a role
@receiver(post_save, sender=User)
def add_user_to_group(sender, instance, created, **kwargs):
    if created:
        instance.groups.add(instance.group)
