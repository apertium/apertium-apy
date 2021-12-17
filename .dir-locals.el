;;; Directory Local Variables
;;; For more information see (info "(emacs) Directory Variables")

((nil .((flycheck-flake8-maximum-line-length .180)))
 (python-mode .((flycheck-python-mypy-args .("run" "mypy" "--check-untyped-defs" "--python-version" "3.8"))
                 (flycheck-python-mypy-executable ."pipenv"))))
