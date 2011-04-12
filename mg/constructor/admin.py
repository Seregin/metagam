from mg import *
from mg.core.auth import UserPermissions, UserPermissionsList
from mg.core.queue import QueueTask, QueueTaskList, Schedule
from mg.core.cluster import TempFileList
from mg.constructor.players import Player, Character, CharacterForm, CharacterList
import mg.constructor.common
from mg.constructor.common import Project, ProjectList
from uuid import uuid4
import time
import datetime

class ConstructorUtils(Module):
    def register(self):
        Module.register(self)
        self.rhook("menu-admin-top.list", self.menu_admin_top_list, priority=-500)

    def menu_admin_top_list(self, topmenu):
        topmenu.append({"href": "http://www.%s/forum" % self.app().inst.config["main_host"], "text": self._("Forum"), "tooltip": self._("Go to the Constructor forum")})
        topmenu.append({"href": "http://www.%s/cabinet" % self.app().inst.config["main_host"], "text": self._("Cabinet"), "tooltip": self._("Return to the Cabinet")})

class Constructor(Module):
    def register(self):
        Module.register(self)
        self.rdep(["mg.core.web.Web"])
        self.rdep(["mg.socio.Socio", "mg.socio.Forum", "mg.admin.AdminInterface", "mg.socio.ForumAdmin",
            "mg.core.auth.Sessions", "mg.core.auth.Interface", "mg.core.cluster.Cluster",
            "mg.core.emails.Email", "mg.core.queue.Queue", "mg.core.cass_maintenance.CassandraMaintenance", "mg.admin.wizards.Wizards",
            "mg.core.projects.Projects",
            "mg.constructor.admin.ConstructorUtils", "mg.game.money.Money", "mg.constructor.dashboard.ProjectDashboard",
            "mg.constructor.domains.Domains", "mg.constructor.domains.DomainsAdmin", "mg.game.money.TwoPay", "mg.constructor.design.SocioInterface",
            "mg.constructor.interface.Dynamic",
            "mg.constructor.doc.Documentation", "mg.core.sites.Counters", "mg.core.sites.CountersAdmin",
            "mg.core.realplexor.RealplexorAdmin", "mg.core.emails.EmailAdmin",
            "mg.socio.telegrams.Telegrams", "mg.core.daemons.Daemons", "mg.core.daemons.DaemonsAdmin",
            "mg.core.cluster.ClusterAdmin", "mg.constructor.auth.AuthAdmin"])
        self.rhook("web.setup_design", self.web_setup_design)
        self.rhook("ext-index.index", self.index, priv="public")
        self.rhook("ext-cabinet.index", self.cabinet_index, priv="logged")
        self.rhook("auth.redirects", self.redirects)
        self.rhook("ext-cabinet.settings", self.cabinet_settings, priv="logged")
        self.rhook("ext-debug.validate", self.debug_validate, priv="public")
        self.rhook("ext-constructor.newgame", self.constructor_newgame, priv="logged")
        self.rhook("objclasses.list", self.objclasses_list)
        self.rhook("all.schedule", self.schedule)
        self.rhook("projects.cleanup_inactive", self.cleanup_inactive)
        self.rhook("core.appfactory", self.appfactory)
        self.rhook("core.webdaemon", self.webdaemon)
        self.rhook("project.title", self.project_title)
        self.rhook("forum-admin.init-categories", self.forum_init_categories)
        self.rhook("projects.list", self.projects_list)
        self.rhook("projects.owned_by", self.projects_owned_by)
        self.rhook("project.cleanup", self.cleanup)
        self.rhook("project.missing", self.missing)
        self.rhook("web.universal_variables", self.universal_variables)
        self.rhook("auth.register-form", self.register_form)
        self.rhook("auth.password-changed", self.password_changed)
        self.rhook("ext-test.delay", self.test_delay, priv="disabled")
        self.rhook("indexpage.render", self.indexpage_render)
        self.rhook("telegrams.params", self.telegrams_params)
        self.rhook("email.sender", self.email_sender)

    def test_delay(self):
        Tasklet.sleep(20)
        self.call("web.response", "ok\n")

    def register_form(self, form, mode):
        req = self.req()
        age18 = req.param("age18")
        if mode == "validate":
            if not age18:
                form.error("age18", self._("You must confirm you are of the full legal age"))
        elif mode == "render":
            form.checkbox(self._("I confirm I'm of the full legal age"), "age18", age18)

    def missing(self, tag):
        app = self.app().inst.appfactory.get_by_tag(tag)
        return app is None

    def forum_init_categories(self, cats):
        cats.append({"id": uuid4().hex, "topcat": self._("Constructor"), "title": self._("News"), "description": self._("News related to the Constructor"), "order": 10.0, "default_subscribe": True})
        cats.append({"id": uuid4().hex, "topcat": self._("Constructor"), "title": self._("Support"), "description": self._("Constructor technical support"), "order": 20.0})
        cats.append({"id": uuid4().hex, "topcat": self._("Game Development"), "title": self._("Developers club"), "description": self._("Any talks related to the game development"), "order": 30.0})

    def project_title(self):
        return "MMO Constructor"

    def appfactory(self):
        raise Hooks.Return(mg.constructor.common.ApplicationFactory(self.app().inst))

    def webdaemon(self):
        raise Hooks.Return(mg.constructor.common.MultiapplicationWebDaemon(self.app().inst))

    def objclasses_list(self, objclasses):
        objclasses["Project"] = (Project, ProjectList)

    def projects_list(self, projects):
        projects.append({"uuid": "main"})
        list = self.app().inst.int_app.objlist(ProjectList, query_index="created")
        list.load(silent=True)
        projects.extend(list.data())

    def projects_owned_by(self, owner, projects):
        list = self.app().inst.int_app.objlist(ProjectList, query_index="owner", query_equal=owner)
        list.load(silent=True)
        projects.extend(list.data())

    def schedule(self, sched):
        sched.add("projects.cleanup_inactive", "10 1 * * *", priority=10)

    def cleanup_inactive(self):
        inst = self.app().inst
        projects = inst.int_app.objlist(ProjectList, query_index="inactive", query_equal="1", query_finish=self.now(-30 * 86400))
        for project in projects:
            self.info("Removing inactive project %s", project.uuid)
            self.call("project.cleanup", project.uuid)

    def web_setup_design(self, vars):
        req = self.req()
        topmenu = []
        cabmenu = []
        if vars.get("global_html"):
            return
        if req.group == "index" and req.hook == "index":
            vars["global_html"] = "constructor/index_global.html"
        elif req.group == "constructor" and req.hook == "newgame":
            vars["global_html"] = "constructor/cabinet_global.html"
            cabmenu.append({"title": self._("Return to the Cabinet"), "href": "/cabinet", "image": "/st/constructor/cabinet/constructor.gif"})
        elif req.group == "socio" and req.hook == "image":
            vars["global_html"] = "constructor/socio_simple_global.html"
        elif req.group == "auth":
            if req.hook == "change" or req.hook == "email":
                vars["global_html"] = "constructor/cabinet_global.html"
                vars["ToTheMainPage"] = self._("To the main page")
                if req.hook == "change":
                    cabmenu.append({"title": self._("Password changing"), "left": True})
                elif req.hook == "email":
                    cabmenu.append({"title": self._("E-mail changing"), "left": True})
                cabmenu.append({"image": "/st/constructor/cabinet/settings.gif", "title": self._("Return to the Settings"), "href": "/cabinet/settings"})
            else:
                vars["global_html"] = "constructor/index_global.html"
        elif req.group == "cabinet":
            vars["global_html"] = "constructor/cabinet_global.html"
            vars["ToTheMainPage"] = self._("To the main page")
            if req.hook == "settings":
                cabmenu.append({"title": self._("Settings"), "left": True})
                cabmenu.append({"title": self._("Return to the Cabinet"), "href": "/cabinet", "image": "/st/constructor/cabinet/constructor.gif"})
            elif req.hook == "index":
                user = self.obj(User, req.user())
                cabmenu.append({"image": "/st/constructor/cabinet/doc.gif", "title": self._("Documentation"), "href": "/doc", "left": True})
                cabmenu.append({"image": "/st/constructor/cabinet/settings.gif", "title": self._("Settings"), "href": "/cabinet/settings", "left": True})
                cabmenu.append({"image": "/st/constructor/cabinet/forum.gif", "title": self._("Forum"), "href": "/forum", "left": True})
                links = []
                self.call("telegrams.menu", links)
                for link in links:
                    cabmenu.append({"image": "/st/constructor/cabinet/telegrams%s.gif" % ("-act" if link["suffix"] else ""), "title": link["html"], "href": link["href"], "left": True, "suffix": link["suffix"]})
                cabmenu.append({"image": "/st/constructor/cabinet/logout.gif", "title": self._("Logout %s") % htmlescape(user.get("name")), "href": "/auth/logout"})
        elif req.group == "forum" or req.group == "socio":
            vars["global_html"] = "constructor/socio_global.html"
            vars["title_suffix"] = " - %s" % self._("MMO Constructor Forum")
            redirect = req.param("redirect")
            redirect_param = True
            if redirect is None or redirect == "":
                redirect = req.uri()
                redirect_param = False
            redirect = urlencode(redirect)
            if req.hook == "settings":
                pass
            else:
                topmenu.append({"search": True, "button": self._("socio-top///Search")})
                if req.user():
                    topmenu.append({"href": "/forum/settings?redirect=%s" % redirect, "image": "/st/constructor/cabinet/settings.gif", "html": self._("Forum settings")})
                    links = []
                    self.call("telegrams.menu", links)
                    for link in links:
                        topmenu.append({"image": "/st/constructor/cabinet/telegrams%s.gif" % ("-act" if link["suffix"] else ""), "html": link["html"], "href": link["href"], "suffix": link["suffix"]})
                    topmenu.append({"href": "/cabinet", "image": "/st/constructor/cabinet/constructor.gif", "html": self._("Return to the Cabinet")})
                else:
                    topmenu.append({"href": "/auth/login?redirect=%s" % redirect, "html": self._("Log in")})
                    topmenu.append({"href": "/auth/register?redirect=%s" % redirect, "html": self._("Register")})
            if redirect_param:
                topmenu.append({"href": htmlescape(req.param("redirect")), "html": self._("Cancel")})
        elif req.group == "telegrams":
            vars["global_html"] = "constructor/socio_global.html"
            vars["title_suffix"] = " - %s" % self._("MMO Constructor")
            topmenu.append({"href": "/forum", "image": "/st/constructor/cabinet/forum.gif", "html": self._("Forum")})
            links = []
            self.call("telegrams.menu", links)
            for link in links:
                topmenu.append({"image": "/st/constructor/cabinet/telegrams%s.gif" % ("-act" if link["suffix"] else ""), "html": link["html"], "href": link["href"], "suffix": link["suffix"]})
            topmenu.append({"href": "/cabinet", "image": "/st/constructor/cabinet/constructor.gif", "html": self._("Cabinet")})
        elif req.group == "doc":
            vars["global_html"] = "constructor/socio_global.html"
            topmenu.append({"href": "/forum", "image": "/st/constructor/cabinet/forum.gif", "html": self._("Forum")})
            if req.user():
                topmenu.append({"href": "/cabinet", "image": "/st/constructor/cabinet/constructor.gif", "html": self._("Return to the Cabinet")})
            topmenu.append({"html": self._("MMO Constructor Documentation"), "header": True, "left": True})
        elif req.group == "admin":
            vars["global_html"] = "constructor/admin_global.html"
        # Topmenu
        if len(topmenu):
            topmenu_left = []
            topmenu_right = []
            for ent in topmenu:
                if ent.get("left"):
                    topmenu_left.append(ent)
                else:
                    topmenu_right.append(ent)
            if len(topmenu_left):
                topmenu_left[-1]["lst"] = True
                vars["topmenu_left"] = topmenu_left
            if len(topmenu_right):
                topmenu_right[-1]["lst"] = True
                vars["topmenu_right"] = topmenu_right
        # Cabmenu
        if len(cabmenu):
            cabmenu_left = []
            cabmenu_right = []
            first_left = True
            first_right = True
            for ent in cabmenu:
                if ent.get("left"):
                    cabmenu_left.append(ent)
                else:
                    cabmenu_right.append(ent)
            if len(cabmenu_left):
                cabmenu_left[-1]["lst"] = True
                vars["cabmenu_left"] = cabmenu_left
            if len(cabmenu_right):
                cabmenu_right[-1]["lst"] = True
                vars["cabmenu_right"] = cabmenu_right

    def universal_variables(self, vars):
        vars["ConstructorTitle"] = self._("Browser-based Games Constructor")
        vars["ConstructorCopyright"] = self._("Copyright &copy; Joy Team, 2009-%s") % datetime.datetime.utcnow().strftime("%Y")

    def redirects(self, tbl):
        tbl["login"] = "/cabinet"
        tbl["register"] = "/cabinet"
        tbl["change"] = "/cabinet/settings"

    def index(self):
        req = self.req()
        vars = {
            "title": self._("Constructor of browser-based online games"),
            "login": self._("log in"),
            "register": self._("register"),
            "forum": self._("forum"),
            "cabinet": self._("cabinet"),
            "logout": self._("log out"),
            "documentation": self._("documentation"),
        }
        if req.user():
            vars["logged"] = True
        self.call("web.response_template", "constructor/index.html", vars)

    def cabinet_index(self):
        req = self.req()
        menu = []
        menu_projects = []
        # constructor admin
        perms = req.permissions()
        if len(perms):
            menu_projects.append({"href": "/admin", "image": "/st/constructor/cabinet/untitled.gif", "text": self._("Constructor administration")})
        # list of games
        projects = self.app().inst.int_app.objlist(ProjectList, query_index="owner", query_equal=req.user())
        projects.load(silent=True)
        comment = None
        if len(projects):
            for project in projects:
                title = project.get("title_short")
                if title is None:
                    title = self._("Untitled game")
                href = None
                domain = project.get("domain")
                if domain is None:
                    domain = "%s.%s" % (project.uuid, self.app().inst.config["main_host"])
                else:
                    domain = "www.%s" % domain
                    if not project.get("admin_confirmed"):
                        self.debug("Project %s (%s) administrator is not confirmed", project.uuid, project.get("created"))
                        app = self.app().inst.appfactory.get_by_tag(project.uuid)
                        admins = app.objlist(CharacterList, query_index="admin", query_equal="1")
                        admins.load()
                        for admin in admins:
                            self.debug("Character %s is admin", admin.uuid)
                            character_user = app.obj(User, admin.uuid)
                            player_user = app.obj(User, admin.get("player"))
                            self.debug("Player %s is admin", player_user.uuid)
                            if player_user.get("inactive"):
                                self.debug("Player is INACTIVE")
                                href = "http://%s/auth/activate/%s?code=%s&okget=1" % (domain, player_user.uuid, player_user.get("activation_code"))
                        comment = self._("Congratulations! Your game was registered successfully. Now you can enter administration panel and configure your game. Don't worry if you can't open your game right now. DNS system is quite slow and it may take several hours or even days for your domain to work.")
                if href is None:
                    href = "http://%s" % domain
                logo = project.get("logo")
                if logo is None:
                    logo = "/st/constructor/cabinet/untitled.gif"
                menu_projects.append({"href": href, "image": logo, "text": title})
                if len(menu_projects) >= 4:
                    menu.append(menu_projects)
                    menu_projects = []
        if len(menu_projects):
            menu.append(menu_projects)
        vars = {
            "title": self._("Cabinet"),
            "cabinet_menu": menu if len(menu) else None,
            "cabinet_leftbtn": {
                "href": "/constructor/newgame",
                "title": self._("Create a new game")
            },
            "cabinet_comment": comment,
        }
        self.call("web.response_global", None, vars)

    def cabinet_settings(self):
        vars = {
            "title": self._("MMO Constructor Settings"),
            "cabinet_menu": [
                [
                    { "href": "/auth/change", "image": "/st/constructor/cabinet/untitled.gif", "text": self._("Change password") },
                    { "href": "/auth/email", "image": "/st/constructor/cabinet/untitled.gif", "text": self._("Change e-mail") },
                    { "href": "/forum/settings?redirect=/cabinet/settings", "image": "/st/constructor/cabinet/untitled.gif", "text": self._("Forum settings") },
#                    { "href": "/constructor/certificate", "image": "/st/constructor/cabinet/untitled.gif", "text": self._("WebMoney Certification") },
                ],
            ],
        }
        self.call("web.response_global", None, vars)

    def debug_validate(self):
        req = self.req()
        slices_list = self.call("cassmaint.load_database")
#        for slice in slices_list:
#            self.debug("KEY: %s", slice.key)
        inst = self.app().inst
        valid_keys = inst.int_app.hooks.call("cassmaint.validate", slices_list)
        slices_list = [row for row in slices_list if row.key not in valid_keys]
        apps = []
        self.call("applications.list", apps)
        for ent in apps:
            tag = ent["tag"]
            self.debug("validating application %s", tag)
            app = inst.appfactory.get_by_tag(tag)
            if app is not None:
                valid_keys = app.hooks.call("cassmaint.validate", slices_list)
                slices_list = [row for row in slices_list if row.key not in valid_keys]
        timestamp = time.time() * 1000
        mutations = {}
        for row in slices_list:
            if len(row.columns):
                for ent in apps:
                    if row.key.startswith("%s-" % ent["tag"]):
                        self.warning("Unknown database key %s", row.key)
                        mutations[row.key] = {"Objects": [Mutation(deletion=Deletion(timestamp=timestamp))]}
        if len(mutations) and req.args == "delete":
            self.db().batch_mutate(mutations, ConsistencyLevel.QUORUM)
        self.call("web.response_json", {"ok": 1})

    def constructor_newgame(self):
        req = self.req()
        # Registration on invitations
        if self.conf("constructor.invitations"):
            if not self.call("invitation.ok", req.user(), "newproject"):
                invitation = req.param("invitation")
                form = self.call("web.form")
                if req.param("ok"):
                    if not invitation or invitation == "":
                        form.error("invitation", self._("Enter invitation code"))
                    else:
                        err = self.call("invitation.enter", req.user(), "newproject", invitation)
                        if err:
                            form.error("invitation", err)
                    if not form.errors:
                        self.call("web.redirect", "/constructor/newgame")
                form.input(self._("Invitation code"), "invitation", invitation)
                form.submit(None, None, self._("Proceed"))
                form.add_message_top(self._("Open registration of new games is unavailable at the moment. If you have an invitation code enter it now"))
                vars = {
                    "title": self._("Invitation required"),
                }
                self.call("web.response_global", form.html(), vars)
        inst = self.app().inst
        # creating new project and application
        int_app = inst.int_app
        project = int_app.obj(Project)
        project.set("created", self.now())
        project.set("owner", req.user())
        project.set("inactive", 1)
        project.store()
        # accessing new application
        app = inst.appfactory.get_by_tag(project.uuid)
        # setting up everything
        app.hooks.call("all.check")
        # creating admin user
        old_user = self.obj(User, req.user())
        now_ts = "%020d" % time.time()
        player = app.obj(Player)
        player.set("created", self.now())
        player_user = app.obj(User, player.uuid, {})
        player_user.set("created", now_ts)
        for field in ["email", "salt", "pass_reminder", "pass_hash"]:
            player_user.set(field, old_user.get(field))
        player_user.set("inactive", 1)
        activation_code = uuid4().hex
        player_user.set("activation_code", activation_code)
        player_user.set("activation_redirect", "/admin")
        # creating admin character
        character = app.obj(Character)
        character.set("created", self.now())
        character.set("player", player.uuid)
        character.set("admin", 1)
        character_user = app.obj(User, character.uuid, {})
        character_user.set("last_login", now_ts)
        for field in ["name", "name_lower", "sex"]:
            character_user.set(field, old_user.get(field))
        character_form = app.obj(CharacterForm, character.uuid, {})
        # storing
        player.store()
        player_user.store()
        character.store()
        character_user.store()
        character_form.store()
        # giving permissions
        self.info("Giving project.admin permission to the user %s" % character_user.uuid)
        perms = app.obj(UserPermissions, character_user.uuid, {"perms": {"project.admin": True}})
        perms.sync()
        perms.store()
        # creating setup wizard
        app.hooks.call("wizards.new", "mg.constructor.setup.ProjectSetupWizard")
        self.call("web.redirect", "http://%s/auth/activate/%s?okget=1&code=%s" % (app.domain, player_user.uuid, activation_code))

    def cleanup(self, tag):
        inst = self.app().inst
        int_app = inst.int_app
        app = inst.appfactory.get_by_tag(tag)
        tasks = int_app.objlist(QueueTaskList, query_index="app-at", query_equal=tag)
        tasks.remove()
        sched = int_app.obj(Schedule, tag, silent=True)
        sched.remove()
        project = int_app.obj(Project, tag, silent=True)
        project.remove()
        if app is not None:
            sessions = app.objlist(SessionList, query_index="valid_till")
            sessions.remove()
            users = app.objlist(UserList, query_index="created")
            users.remove()
            perms = app.objlist(UserPermissionsList, users.uuids())
            perms.remove()
            config = app.objlist(ConfigGroupList, query_index="all")
            config.remove()
            hook_modules = app.objlist(HookGroupModulesList, query_index="all")
            hook_modules.remove()
            wizards = app.objlist(WizardConfigList, query_index="all")
            wizards.remove()
        temp_files = int_app.objlist(TempFileList, query_index="app", query_equal=tag)
        temp_files.load(silent=True)
        for file in temp_files:
            file.delete()
        temp_files.remove()

    def password_changed(self, user, password):
        self.info("Changed password of user %s", user.uuid)
        projects = self.app().inst.int_app.objlist(ProjectList, query_index="owner", query_equal=user.uuid)
        projects.load(silent=True)
        for project in projects:
            app = self.app().inst.appfactory.get_by_tag(project.uuid)
            users = app.objlist(UserList, query_index="name", query_equal=user.get("name"))
            users.load(silent=True)
            for u in users:
                self.info("Replicated password to the user %s in the project %s", u.uuid, project.uuid)
                u.set("salt", user.get("salt"))
                u.set("pass_reminder", user.get("pass_reminder"))
                u.set("pass_hash", user.get("pass_hash"))
                u.store()

    def indexpage_render(self, vars):
        fields = [
            {"code": "name", "prompt": self._("Enter your name, please"), "type": 0},
            {"code": "sex", "prompt": self._("What\\'s your sex"), "type": 1, "values": [[0, "Male"], [1, "Female", True]]},
            {"code": "motto", "prompt": self._("This is a very long text asking you to enter your motto. So be so kind entering your motto"), "type": 2},
            {"code": "password", "prompt": self._("Enter your password")},
        ]
        vars["register_fields"] = fields

    def telegrams_params(self, params):
        params["menu_title"] = self._("telegrams menu///Post")
        params["page_title"] = self._("Messages")
        params["last_telegram"] = self._("Last message")
        params["all_telegrams"] = self._("All messages")
        params["send_telegram"] = self._("Send a new message")
        params["text"] = self._("Message text")
        params["system_name"] = self._("MMO Constructor")
        params["telegrams_with"] = self._("Correspondence with {0}")

    def email_sender(self, params):
        params["email"] = "robot@mmoconstructor.ru"
        params["name"] = self._("MMO Constructor")
        params["prefix"] = "[mg] "
        params["signature"] = self._("MMO Constructor - http://www.mmoconstructor.ru - constructor of browser-based online games")
