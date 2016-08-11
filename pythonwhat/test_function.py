import ast

from pythonwhat.Test import Test, DefinedCollTest, EqualTest, EquivalentTest, BiggerTest
from pythonwhat.State import State
from pythonwhat.Reporter import Reporter
from pythonwhat.Feedback import Feedback
from pythonwhat.utils import get_ord, get_num
from pythonwhat.utils_ast import extract_text_from_node
from pythonwhat.tasks import evalInProcess, getSignatureInProcess

def test_function(name,
                  index=1,
                  args=None,
                  keywords=None,
                  eq_condition="equal",
                  do_eval=True,
                  not_called_msg=None,
                  args_not_specified_msg=None,
                  incorrect_msg=None):
    """Test if function calls match.

    This function compares a function call in the student's code with the corresponding one in the solution
    code. It will cause the reporter to fail if the corresponding calls do not match. The fail message
    that is returned will depend on the sort of fail.

    Args:
        name (str): the name of the function to be tested.
        index (int): index of the function call to be checked. Defaults to 1.
        args (list(int)): the indices of the positional arguments that have to be checked. If it is set to
          None, all positional arguments which are in the solution will be checked.
        keywords (list(str)): the indices of the keyword arguments that have to be checked. If it is set to
          None, all keyword arguments which are in the solution will be checked.
        eq_condition (str): The condition which is checked on the eval of the group. Can be "equal" --
          meaning that the operators have to evaluate to exactly the same value, or "equivalent" -- which
          can be used when you expect an integer and the result can differ slightly. Defaults to "equal".
        do_eval (bool): True: arguments are evaluated and compared. False: arguments are not evaluated but
            'string-matched'. None: arguments are not evaluated; it is only checked if they are specified.
        not_called_msg (str): feedback message if the function is not called.
        args_not_specified_msg (str): feedback message if the function is called but not all required arguments are specified
        incorrect_msg (str): feedback message if the arguments of the function in the solution doesn't match
          the one of the student.

    Raises:
        NameError: the eq_condition you passed is not "equal" or "equivalent".
        NameError: function is not called in the solution

    Examples:
        Student code

        | ``import numpy as np``
        | ``np.mean([1,2,3])``
        | ``np.std([2,3,4])``

        Solution code

        | ``import numpy``
        | ``numpy.mean([1,2,3], axis = 0)``
        | ``numpy.std([4,5,6])``

        SCT

        | ``test_function("numpy.mean", index = 1, keywords = [])``: pass.
        | ``test_function("numpy.mean", index = 1)``: fail.
        | ``test_function(index = 1, incorrect_op_msg = "Use the correct operators")``: fail.
        | ``test_function(index = 1, used = [], incorrect_result_msg = "Incorrect result")``: fail.
    """
    state = State.active_state
    rep = Reporter.active_reporter
    rep.set_tag("fun", "test_function")

    index = index - 1

    eq_map = {"equal": EqualTest, "equivalent": EquivalentTest}
    if eq_condition not in eq_map:
        raise NameError("%r not a valid equality condition " % eq_condition)
    eq_fun = eq_map[eq_condition]

    student_process, solution_process = state.student_process, state.solution_process

    state.extract_function_calls()
    solution_calls = state.solution_function_calls
    student_calls = state.student_function_calls
    student_mappings = state.student_mappings

    # for messaging purposes: replace with original alias or import again.
    stud_name = get_mapped_name(name, student_mappings)

    if not_called_msg is None:
        if index == 0:
            not_called_msg = "Have you called `%s()`?" % stud_name
        else:
            not_called_msg = ("The system wants to check the %s call of `%s()`, " +
                "but hasn't found it; have another look at your code.") % (get_ord(index + 1), stud_name)

    if name not in solution_calls or len(solution_calls[name]) <= index:
        raise NameError("%r not in solution environment (often enough)" % name)

    rep.do_test(DefinedCollTest(name, student_calls, not_called_msg))
    if rep.failed_test:
        return

    rep.do_test(BiggerTest(len(student_calls[name]), index, not_called_msg))
    if rep.failed_test:
        return

    solution_call, args_solution, keyw_solution = solution_calls[name][index]
    keyw_solution = {keyword.arg: keyword.value for keyword in keyw_solution}


    if args is None:
        args = list(range(len(args_solution)))

    if keywords is None:
        keywords = list(keyw_solution.keys())

    if len(args) > 0 or len(keywords) > 0:

        success = None

        # Get all options (some function calls may be blacklisted)
        call_indices = state.get_options(name, list(range(len(student_calls[name]))), index)

        feedback = None

        for call_ind in call_indices:
            student_call, args_student, keyw_student = student_calls[name][call_ind]
            keyw_student = {keyword.arg: keyword.value for keyword in keyw_student}

            success = True
            start = "Have you specified all required arguments inside `%s()`?" % stud_name

            if len(args) > 0 and (max(args) >= len(args_student)):
                if feedback is None:
                    if not args_not_specified_msg:
                        n = max(args)
                        if n == 0:
                            args_not_specified_msg = start + " You should specify one argument without naming it."
                        else:
                            args_not_specified_msg = start + (" You should specify %s arguments without naming them." % get_num(n + 1))
                    feedback = Feedback(args_not_specified_msg, student_call)
                success = False
                continue

            setdiff = list(set(keywords) - set(keyw_student.keys()))
            if len(setdiff) > 0:
                if feedback is None:
                    if not args_not_specified_msg:
                        args_not_specified_msg = start + " You should specify the keyword `%s` explicitly by its name." % setdiff[0]
                    feedback = Feedback(args_not_specified_msg, student_call)
                success = False
                continue

            if do_eval is None:
                # don't have to go further: set used and break from the for loop
                state.set_used(name, call_ind, index)
                break

            feedback_msg = "Did you call `%s()` with the correct arguments?" % stud_name
            for arg in args:
                arg_student = args_student[arg]
                arg_solution = args_solution[arg]
                if incorrect_msg is None:
                    msg = feedback_msg + (" The %s argument seems to be incorrect." % get_ord(arg + 1))
                    add_more = True
                else:
                    msg = incorrect_msg
                    add_more = False

                test = build_test(arg_student, arg_solution,
                                  student_process, solution_process,
                                  do_eval, eq_fun, msg, add_more=add_more)
                test.test()

                if not test.result:
                    if feedback is None:
                        feedback = test.get_feedback()
                    success = False
                    break

            if success:
                for key in keywords:
                    key_student = keyw_student[key]
                    key_solution = keyw_solution[key]
                    if incorrect_msg is None:
                        msg = feedback_msg + (" Keyword `%s` seems to be incorrect." % key)
                        add_more = True
                    else:
                        msg = incorrect_msg
                        add_more = False

                    test = build_test(key_student, key_solution,
                                      student_process, solution_process,
                                      do_eval, eq_fun, msg, add_more=add_more)
                    test.test()

                    if not test.result:
                        if feedback is None:
                            feedback = test.get_feedback()
                        success = False
                        break

            if success:
                # we have a winner that passes all argument and keyword checks
                state.set_used(name, call_ind, index)
                break

        if not success:
            if feedback is None:
                feedback = Feedback("You haven't used enough appropriate calls of `%s()`" % stud_name)
            rep.do_test(Test(feedback))

def test_print(index = 1,
               do_eval=True,
               eq_condition="equal",
               not_called_msg="Have you called `print()`?",
               params_not_matched_msg="Have you correctly called `print()`?",
               params_not_specified_msg="Have you correctly called `print()`?",
               incorrect_msg="Have you printed out the correct object?"):
    test_function_v2("print",
                     index=index,
                     params=["value"],
                     signature=None,
                     eq_condition=eq_condition,
                     do_eval=do_eval,
                     not_called_msg=not_called_msg,
                     params_not_matched_msg=params_not_matched_msg,
                     params_not_specified_msg=params_not_specified_msg,
                     incorrect_msg=incorrect_msg)
    """Test print() calls

    Utility function to test the print() function. For arguments, check test_function_v2()
    """

def test_function_v2(name,
                     index=1,
                     params=[],
                     signature=None,
                     eq_condition="equal",
                     do_eval=True,
                     not_called_msg=None,
                     params_not_matched_msg=None,
                     params_not_specified_msg=None,
                     incorrect_msg=None):
    """Test if function calls match (v2).

    This function compares a function call in the student's code with the corresponding one in the solution
    code. It will cause the reporter to fail if the corresponding calls do not match. The fail message
    that is returned will depend on the sort of fail.

    Args:
        name (str): the name of the function to be tested.
        index (int): index of the function call to be checked. Defaults to 1.
        params (list(str)): the parameter names of the function call that you want to check.
        signature (Signature): Normally, test_function() can figure out what the function signature is,
            but it might be necessary to use build_sig to manually build a signature and pass this along.
        eq_condition (str): How objects should be compared ("equal" or "equivalent")
        do_eval (list(bool)): Boolean or list of booleans (parameter-specific) that specify whether or
            not arguments should be evaluated.
            True: arguments are evaluated and compared.
            False: arguments are not evaluated but 'string-matched'.
            None: arguments are not evaluated; it is only checked if they are specified.
        not_called_msg (str): custom feedback message if the function is not called.
        params_not_matched_message (str): custom feedback message if the function parameters were not successfully matched.
        params_not_specified_msg (str): string or list of strings (parameter-specific). Custom feedback message if not all
            parameters listed in params are specified by the student.
        incorrect_msg (list(str)): string or list of strings (parameter-specific). Custom feedback messages if the arguments
            don't correspond between student and solution code.
    """

    state = State.active_state
    rep = Reporter.active_reporter
    rep.set_tag("fun", "test_function")

    index = index - 1
    eq_map = {"equal": EqualTest, "equivalent": EquivalentTest}
    if eq_condition not in eq_map:
        raise NameError("%r not a valid equality condition " % eq_condition)
    eq_fun = eq_map[eq_condition]

    if not isinstance(params, list):
        raise NameError("Inside test_function_v2, make sure to specify a LIST of params.")

    if isinstance(do_eval, bool) or do_eval is None:
        do_eval = [do_eval] * len(params)

    if len(params) != len(do_eval):
        raise NameError("Inside test_function_v2, make sure that do_eval has the same length as params.")

    # if params_not_specified_msg is a str or None, convert into list
    if isinstance(params_not_specified_msg, str) or params_not_specified_msg is None:
        params_not_specified_msg = [params_not_specified_msg] * len(params)

    if len(params) != len(params_not_specified_msg):
        raise NameError("Inside test_function_v2, make sure that params_not_specified_msg has the same length as params.")

    # if incorrect_msg is a str or None, convert into list
    if isinstance(incorrect_msg, str) or incorrect_msg is None:
        incorrect_msg = [incorrect_msg] * len(params)

    if len(params) != len(incorrect_msg):
        raise NameError("Inside test_function_v2, make sure that incorrect_msg has the same length as params.")

    student_process, solution_process = state.student_process, state.solution_process

    state.extract_function_calls()
    solution_calls = state.solution_function_calls
    student_calls = state.student_function_calls
    student_mappings = state.student_mappings
    solution_mappings = state.solution_mappings

    stud_name = get_mapped_name(name, student_mappings)
    sol_name = get_mapped_name(name, solution_mappings)

    if not_called_msg is None:
        if index == 0:
            not_called_msg = "Have you called `%s()`?" % stud_name
        else:
            not_called_msg = ("The system wants to check the %s call of `%s()`, " +
                "but hasn't found it; have another look at your code.") % (get_ord(index + 1), stud_name)

    if name not in solution_calls or len(solution_calls[name]) <= index:
        raise NameError("%r not in solution environment (often enough)" % name)

    rep.do_test(DefinedCollTest(name, student_calls, not_called_msg))
    if rep.failed_test:
        return

    rep.do_test(BiggerTest(len(student_calls[name]), index, not_called_msg))
    if rep.failed_test:
        return

    if len(params) > 0:

        try:
            sol_call, arguments, keywords = solution_calls[name][index]
            sol_sig = getSignatureInProcess(name=name, mapped_name=sol_name,
                                            signature=signature,
                                            manual_sigs = State.active_state.get_manual_sigs(),
                                            process=solution_process)
            solution_args, _ = bind_args(signature = sol_sig, arguments=arguments, keyws=keywords)
        except:
            raise ValueError(("Something went wrong in matching the %s call of %s to its signature." + \
                " You might have to manually specify or correct the function signature.") % (get_ord(index + 1), sol_name))

        if len(list(set(params) - set(solution_args.keys()))) > 0:
            raise ValueError("When testing %s(), the solution call doesn't specify the listed parameters." % name)

        success = None

        # Get all options (some function calls may be blacklisted)
        call_indices = state.get_options(name, list(range(len(student_calls[name]))), index)

        feedback = None

        for call_ind in call_indices:

            # let's start with assuming all is good
            success = True

            try:
                student_call, arguments, keywords = student_calls[name][call_ind]
                student_sig = getSignatureInProcess(name = name, mapped_name = stud_name,
                                                    signature=signature,
                                                    manual_sigs = State.active_state.get_manual_sigs(),
                                                    process=student_process)
                student_args, student_params = bind_args(signature = student_sig, arguments=arguments, keyws=keywords)
            except:
                if feedback is None:
                    if not params_not_matched_msg:
                        params_not_matched_msg = ("Something went wrong in figuring out how you specified the " + \
                            "arguments for `%s()`; have another look at your code and its output.") % stud_name
                    feedback = Feedback(params_not_matched_msg, student_call)
                success = False
                continue

            setdiff = list(set(params) - set(student_args.keys()))
            if len(setdiff) > 0:
                if feedback is None:
                    first_missing = setdiff[0]
                    param_ind = params.index(first_missing)
                    if params_not_specified_msg[param_ind] is None:
                        msg = "Have you specified all required arguments inside `%s()`?" % stud_name
                        # only if value can be supplied as keyword argument, give more info:
                        if student_params[first_missing].kind in [1, 3, 4]:
                            msg += " You didn't specify `%s`." % first_missing
                    else:
                        msg = params_not_specified_msg[param_ind]
                    feedback = Feedback(msg, student_call)
                success = False
                continue

            for ind, param in enumerate(params):

                if do_eval[ind] is None:
                    continue

                arg_student = student_args[param]
                arg_solution = solution_args[param]
                if incorrect_msg[ind] is None:
                    msg = "Did you call `%s()` with the correct arguments?" % stud_name
                    # only if value can be supplied as keyword argument, give more info:
                    if student_params[param].kind in [1, 3, 4]:
                            msg += " The argument you specified for `%s` seems to be incorrect." % param
                    add_more = True
                else:
                    msg = incorrect_msg[ind]
                    add_more = False

                test = build_test(arg_student, arg_solution,
                                  student_process, solution_process,
                                  do_eval[ind], eq_fun, msg, add_more)
                test.test()

                if not test.result:
                    if feedback is None:
                        feedback = test.get_feedback()
                    success = False
                    break

            # If all is still good, we have a winner!
            if success:
                state.set_used(name, call_ind, index)
                break

        if not success:
            if feedback is None:
                feedback = Feedback("You haven't used enough appropriate calls of `%s()`." % stud_name)
            rep.do_test(Test(feedback))

def get_mapped_name(name, mappings):
    mapped_name = name
    if "." in mapped_name:
        mappings_rev = {v: k for k, v in mappings.items()}
        els = name.split(".")
        if els[0] in mappings_rev.keys():
                mapped_name = ".".join([mappings_rev[els[0]]] + els[1:])
    return(mapped_name)

def bind_args(signature, arguments, keyws):
    keyws = {keyword.arg: keyword.value for keyword in keyws}
    bound_args = signature.bind(*arguments, **keyws)
    return(bound_args.arguments, signature.parameters)

def build_test(stud, sol, student_process, solution_process, do_eval, eq_fun, feedback_msg, add_more):
    got_error = False
    if do_eval:

        eval_student = evalInProcess(stud, student_process)
        if eval_student is None:
            got_error = True

        eval_solution = evalInProcess(sol, solution_process)
        # import pdb; pdb.set_trace()
        if eval_solution is None:
            raise ValueError("Something went wrong in figuring out arguments")

        # The (eval_student, ) part is important, because when eval_student is a tuple, we don't want
        # to expand them all over the %'s during formatting, we just want the tuple to be represented
        # in the place of the %r. Same for eval_solution.
        # if add_more:
        #     if got_error:
        #         feedback_msg += " Expected `%r`, but got %s." % (eval_solution, "an error")
        #     else:
        #         feedback_msg += " Expected `%r`, but got `%r`." % (eval_solution, eval_student)
    else:
        # We don't want the 'expected...' message here. It's a pain in the ass to deparse the ASTs to
        # give something meaningful.
        eval_student = ast.dump(stud)
        eval_solution = ast.dump(sol)

    return(Test(Feedback(feedback_msg, stud)) if got_error else
        eq_fun(eval_student, eval_solution, Feedback(feedback_msg, stud)))








