#!/usr/bin/env python3
import sys
import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp

gi.require_version("GimpUi", "3.0")
from gi.repository import GimpUi

gi.require_version("GObject", "2.0")
from gi.repository import GObject


class Hellow(Gimp.PlugIn):
    def do_query_procedures(self):
        return ["python-fu-hello_w"]

    def do_create_procedure(self, name):
        procedure = Gimp.ImageProcedure.new(
            self, name, Gimp.PDBProcType.PLUGIN, self.run, None
        )
        procedure.set_image_types("*")
        procedure.set_documentation("Opis", "Opis", name)
        procedure.set_menu_label("Test Generowania")
        procedure.add_menu_path("<Image>/Filters/Development/")

        procedure.add_int_argument(
            "ilosc", "Ilosc", "Ile sztuk", 1, 10, 5, GObject.ParamFlags.READWRITE
        )
        return procedure

    def run(self, procedure, run_mode, image, n_drawables, drawables, args, run_data):
        GimpUi.init("python-fu-hello_w")
        dialog = GimpUi.ProcedureDialog.new(
            procedure, GimpUi.ProcedureDialogMode.RUN, None
        )
        dialog.fill(None)

        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)

        dialog.destroy()
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)


if __name__ == "__main__":
    Gimp.main(Hellow.__gtype__, sys.argv)
